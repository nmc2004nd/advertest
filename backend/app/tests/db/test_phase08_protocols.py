"""Phase 8 Group 1: protocol có version (task 8, 10) và tuân thủ protocol khi ước lượng, tạo
experiment, xem chi tiết (task 9). validation.md mục Protocol, Tuân thủ khi tạo."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from advertest_contracts.enums import ComplianceCode, ProtocolStatus, Role
from advertest_contracts.hashing import sha256_of
from advertest_contracts.models import (
    ErrorResponse,
    ExperimentDetail,
    ProtocolSummary,
    ProtocolView,
)
from attacks.registry import get_spec, load_catalog
from backend.app.db import models as m

from .test_experiment_api import (
    DEV_OPEN,
    Api,
    Fx,
    _body,
    _create,
    _estimate,
    _post,
    api,
    env,
    fx,
    world,
)
from .test_worker_services import _attack

pytestmark = pytest.mark.db
__all__ = ["api", "env", "fx", "world"]
OPENAPI = Path(__file__).resolve().parents[4] / "contracts" / "openapi.json"


def _required(name: str, levels: list[float] | None = None, **search: Any) -> dict[str, Any]:
    spec = get_spec(load_catalog(), name=name)
    body: dict[str, Any] = {"attack_spec_name": name, "spec_sha256": spec.spec_sha256}
    if search:
        param = spec.primary_param
        body.update(
            mode="search",
            search={
                "threshold_kind": "relative_drop", "threshold": 0.2, "lo": param.min,
                "hi": param.max, "max_tol": (param.max - param.min) / 64, **search,
            },
        )  # fmt: skip
    else:
        body.update(mode="grid", grid={"levels": levels or [4]})
    return body


def _protocol_body(
    attacks: list[dict[str, Any]] | None = None, *, min_slice_size: int = 2, **extra: Any
) -> dict[str, Any]:
    attacks = attacks if attacks is not None else [_required("fgsm", [2, 4])]
    first = attacks[0]
    level = first["grid"]["levels"][0] if first["mode"] == "grid" else first["search"]["hi"]
    kind = "max_drop_at_level" if first["mode"] == "grid" else "min_breaking_point"
    criterion: dict[str, Any] = {
        "kind": kind, "attack_spec_name": first["attack_spec_name"], "level": level,
        "threshold_kind": "relative_drop", "threshold": 0.2,
    }  # fmt: skip
    return {
        "description": "Protocol thử nghiệm",
        "required_attacks": attacks,
        "min_slice_size": min_slice_size,
        "pass_criteria": [criterion],
        **extra,
    }


def _name() -> str:
    return f"p8-{uuid.uuid4().hex[:8]}"


def _create_protocol(client: TestClient, body: dict[str, Any] | None = None) -> ProtocolView:
    response = _post(client, "/protocols", {"name": _name(), "body": body or _protocol_body()})
    assert response.status_code == 201, response.text
    return ProtocolView.model_validate(response.json())


def _error(response: httpx.Response) -> tuple[int, str, list[str]]:
    error = ErrorResponse.model_validate(response.json()).error
    return response.status_code, error.code, [f.path for f in error.fields or []]


def _audit(engine: Engine, entity: uuid.UUID, action: str) -> int:
    with Session(engine) as s:
        return (
            s.scalar(
                select(func.count())
                .select_from(m.AuditLog)
                .where(m.AuditLog.entity_id == entity, m.AuditLog.action == action)
            )
            or 0
        )


# ---------------------------------------------------------------- protocol (task 8, 10)


def test_reviewer_creates_active_version_1(api: Api, fx: Fx, app_engine: Engine) -> None:
    reviewer, client = api.client(Role.REVIEWER)
    view = _create_protocol(client)
    assert (view.status, view.version) == (ProtocolStatus.ACTIVE, 1)
    assert view.created_by is not None and view.created_by.id == reviewer
    assert view.body_sha256 == sha256_of(view.body)
    assert _audit(app_engine, view.id, "protocol.created") == 1
    got = client.get(f"/protocols/{view.id}")
    assert ProtocolView.model_validate(got.json()) == view


@pytest.mark.parametrize("role", [Role.ENGINEER, Role.ADMIN])
def test_only_reviewer_creates(api: Api, fx: Fx, role: Role) -> None:
    _, client = api.client(role)
    response = _post(client, "/protocols", {"name": _name(), "body": _protocol_body()})
    assert _error(response)[:2] == (403, "forbidden")


def test_duplicate_name_is_conflict(api: Api, fx: Fx) -> None:
    _, client = api.client(Role.REVIEWER)
    view = _create_protocol(client)
    response = _post(client, "/protocols", {"name": view.name, "body": _protocol_body()})
    assert _error(response)[:2] == (409, "conflict")


def test_new_version_keeps_old_and_retires_it(api: Api, fx: Fx, app_engine: Engine) -> None:
    _, client = api.client(Role.REVIEWER)
    v1 = _create_protocol(client)
    body = _protocol_body([_required("fgsm", [2, 4, 8])])
    response = _post(client, f"/protocols/{v1.id}/versions", {"body": body})
    assert response.status_code == 201, response.text
    v2 = ProtocolView.model_validate(response.json())
    assert (v2.name, v2.version, v2.status) == (v1.name, 2, ProtocolStatus.ACTIVE)
    old = ProtocolView.model_validate(client.get(f"/protocols/{v1.id}").json())
    assert old.status == ProtocolStatus.RETIRED
    assert old.body == v1.body and old.body_sha256 == v1.body_sha256 == sha256_of(old.body)
    assert _audit(app_engine, v2.id, "protocol.versioned") == 1
    assert _audit(app_engine, v1.id, "protocol.retired") == 1
    # Chỉ tạo version từ bản mới nhất.
    again = _post(client, f"/protocols/{v1.id}/versions", {"body": body})
    assert _error(again)[:2] == (409, "conflict")


def test_retire_and_list(api: Api, fx: Fx) -> None:
    _, client = api.client(Role.REVIEWER)
    view = _create_protocol(client)
    response = _post(client, f"/protocols/{view.id}/retire")
    assert response.status_code == 200
    assert ProtocolView.model_validate(response.json()).status == ProtocolStatus.RETIRED
    assert _error(_post(client, f"/protocols/{view.id}/retire"))[:2] == (409, "conflict")
    listed = {ProtocolSummary.model_validate(p).id for p in client.get("/protocols").json()}
    assert view.id not in listed and uuid.UUID(DEV_OPEN) in listed
    every = client.get("/protocols", params={"include_retired": "true"}).json()
    assert view.id in {ProtocolSummary.model_validate(p).id for p in every}


def test_dev_open_has_no_versions(api: Api, fx: Fx) -> None:
    _, client = api.client(Role.REVIEWER)
    response = _post(client, f"/protocols/{DEV_OPEN}/versions", {"body": _protocol_body()})
    assert _error(response)[:2] == (409, "conflict")
    assert _error(_post(client, f"/protocols/{DEV_OPEN}/retire"))[:2] == (409, "conflict")
    view = ProtocolView.model_validate(client.get(f"/protocols/{DEV_OPEN}").json())
    assert view.status == ProtocolStatus.DEV and view.created_by is None


def test_unknown_protocol_is_404(api: Api, fx: Fx) -> None:
    _, client = api.client(Role.REVIEWER)
    assert client.get(f"/protocols/{uuid.uuid4()}").status_code == 404
    assert _post(client, f"/protocols/{uuid.uuid4()}/retire").status_code == 404


def test_no_endpoint_edits_a_version() -> None:
    paths = json.loads(OPENAPI.read_text())["paths"]
    for path, ops in paths.items():
        if path.startswith("/protocols"):
            assert not {"put", "patch", "delete"} & set(ops), path


@pytest.mark.parametrize(
    ("attack", "path"),
    [
        ({**_required("fgsm"), "spec_sha256": "0" * 64}, "body.required_attacks.0.spec_sha256"),
        ({**_required("fgsm"), "attack_spec_name": "khong_co"}, None),
        (_required("fgsm", [64]), "body.required_attacks.0.grid.levels"),
        (_required("fog", [7]), "body.required_attacks.0.grid.levels"),
        (_required("adv_patch", lo=0.05, hi=0.2), "body.required_attacks.0.mode"),
        (_required("fog", lo=1.5, hi=5, max_tol=0.5), "body.required_attacks.0.search.lo"),
    ],
)
def test_catalog_rules_are_422(api: Api, fx: Fx, attack: dict[str, Any], path: str | None) -> None:
    _, client = api.client(Role.REVIEWER)
    body = _protocol_body([attack])
    if path is None:  # tên khác: tiêu chí trỏ tới tên mới, spec không có trong catalog
        path = "body.required_attacks.0.spec_sha256"
    status, code, paths = _error(_post(client, "/protocols", {"name": _name(), "body": body}))
    assert (status, code) == (422, "invalid_request")
    assert path in paths


def test_contract_rules_are_422(api: Api, fx: Fx) -> None:
    _, client = api.client(Role.REVIEWER)
    body = _protocol_body()
    body["pass_criteria"][0]["attack_spec_name"] = "pgd_linf"
    assert _post(client, "/protocols", {"name": _name(), "body": body}).status_code == 422
    body = _protocol_body([_required("pgd_linf", lo=0, hi=32)])
    body["pass_criteria"][0]["kind"] = "max_drop_at_level"
    assert _post(client, "/protocols", {"name": _name(), "body": body}).status_code == 422


def test_max_runs_with_search_points(api: Api, fx: Fx) -> None:
    """Level bắt buộc cộng `max_points` của tìm ngưỡng (tol = max_tol) không vượt 50."""
    _, client = api.client(Role.REVIEWER)
    fine = 32 / 4096
    attacks = [
        _required("pgd_linf", max_tol=fine),
        _required("pgd_l2", max_tol=fine),
        _required("fgsm", max_tol=fine),
        _required("bbox_occlusion", [round(0.05 * (k + 1), 2) for k in range(12)]),
    ]
    status, code, paths = _error(
        _post(client, "/protocols", {"name": _name(), "body": _protocol_body(attacks)})
    )
    assert (status, code, paths) == (422, "invalid_request", ["body.required_attacks"])


# ---------------------------------------------------------------- tuân thủ (task 9)


def _items(error: httpx.Response) -> dict[tuple[ComplianceCode, str | None], bool]:
    body = ErrorResponse.model_validate(error.json()).error
    assert body.code == "not_compliant" and body.compliance is not None
    return {(i.code, i.attack_spec_name): i.satisfied for i in body.compliance}


def _active(api: Api, body: dict[str, Any] | None = None) -> ProtocolView:
    _, reviewer = api.client(Role.REVIEWER)
    return _create_protocol(reviewer, body)


def test_compliant_experiment_is_created_with_compliance(api: Api, fx: Fx) -> None:
    protocol = _active(api)
    _, client = api.client()
    body = _body(fx, attacks=[_attack("fgsm", [2, 4, 8])], protocol_id=str(protocol.id))
    estimate = _estimate(client, body)
    assert estimate.compliance and all(i.satisfied for i in estimate.compliance)
    detail = _create(client, body)
    assert detail.compliance and all(i.satisfied for i in detail.compliance)
    # Mục protocol_active chỉ có khi tạo mới (ước lượng), không có ở chi tiết.
    assert {i.code for i in estimate.compliance} - {i.code for i in detail.compliance} == {
        ComplianceCode.PROTOCOL_ACTIVE
    }


def test_missing_attack_and_level(api: Api, fx: Fx) -> None:
    protocol = _active(api, _protocol_body([_required("fgsm", [2, 4]), _required("pgd_linf")]))
    _, client = api.client()
    body = _body(fx, attacks=[_attack("fgsm", [4, 8])], protocol_id=str(protocol.id))
    response = _post(client, "/experiments", body)
    assert response.status_code == 422
    items = _items(response)
    assert items[(ComplianceCode.ATTACK_PRESENT, "pgd_linf")] is False
    assert items[(ComplianceCode.GRID_LEVELS, "fgsm")] is False
    assert items[(ComplianceCode.ATTACK_PRESENT, "fgsm")] is True
    # Ước lượng trả cùng danh sách, không chặn.
    estimate = _estimate(client, body)
    assert {(i.code, i.attack_spec_name): i.satisfied for i in estimate.compliance} == items


def test_wrong_mode(api: Api, fx: Fx) -> None:
    protocol = _active(api, _protocol_body([_required("pgd_linf", lo=0, hi=32)]))
    _, client = api.client()
    body = _body(fx, attacks=[_attack("pgd_linf", [4])], protocol_id=str(protocol.id))
    assert _items(_post(client, "/experiments", body))[(ComplianceCode.MODE, "pgd_linf")] is False


def test_slice_smaller_than_min(api: Api, fx: Fx) -> None:
    protocol = _active(api, _protocol_body(min_slice_size=1000))
    _, client = api.client()
    body = _body(fx, attacks=[_attack("fgsm", [2, 4])], protocol_id=str(protocol.id))
    assert (
        _items(_post(client, "/experiments", body))[(ComplianceCode.MIN_SLICE_SIZE, None)] is False
    )


def test_model_without_gradients(api: Api, fx: Fx) -> None:
    protocol = _active(api)
    _, client = api.client()
    body = _body(
        fx, attacks=[_attack("fgsm", [2, 4])], protocol_id=str(protocol.id),
        model_version_id=str(fx.nograd_model), class_mapping_id=str(fx.nograd_mapping),
    )  # fmt: skip
    items = _items(_post(client, "/experiments", body))
    assert items[(ComplianceCode.MODEL_GRADIENTS, None)] is False


def test_retired_protocol_keeps_existing_experiment_compliant(api: Api, fx: Fx) -> None:
    protocol = _active(api)
    _, client = api.client()
    body = _body(fx, attacks=[_attack("fgsm", [2, 4])], protocol_id=str(protocol.id))
    detail = _create(client, body)
    _, reviewer = api.client(Role.REVIEWER)
    assert _post(reviewer, f"/protocols/{protocol.id}/retire").status_code == 200
    again = ExperimentDetail.model_validate(client.get(f"/experiments/{detail.id}").json())
    assert again.compliance and all(i.satisfied for i in again.compliance)
    status, code, paths = _error(_post(client, "/experiments", body))
    assert (status, code, paths) == (422, "invalid_request", ["protocol_id"])


def test_dev_open_has_no_compliance(api: Api, fx: Fx) -> None:
    _, client = api.client()
    body = _body(fx, attacks=[_attack("fgsm", [4])])
    assert _estimate(client, body).compliance == []


def test_protocol_ids_are_distinct_rows(app_engine: Engine, api: Api, fx: Fx) -> None:
    """Version mới là bản ghi mới cùng `name` (ràng buộc unique (name, version))."""
    _, client = api.client(Role.REVIEWER)
    v1 = _create_protocol(client)
    _post(client, f"/protocols/{v1.id}/versions", {"body": _protocol_body()})
    with Session(app_engine) as s:
        rows = s.scalars(select(m.Protocol).where(m.Protocol.name == v1.name)).all()
    assert sorted((r.version, r.status) for r in rows) == [
        (1, ProtocolStatus.RETIRED),
        (2, ProtocolStatus.ACTIVE),
    ]


def test_concurrent_duplicate_insert_is_conflict(api: Api, fx: Fx, app_engine: Engine) -> None:
    """Review Group 1 #2: bản thứ hai cùng (name, version) → Conflict (409), không phải 500."""
    from backend.app.protocols import service as protocol_service
    from backend.app.services.errors import Conflict

    reviewer_id, client = api.client(Role.REVIEWER)
    view = _create_protocol(client)
    with Session(app_engine) as s, s.begin():
        actor = s.get(m.User, reviewer_id)
        assert actor is not None
        with pytest.raises(Conflict):
            protocol_service._insert(s, actor=actor, name=view.name, version=1, body=view.body)
        # Giao dịch ngoài vẫn dùng được sau lỗi (savepoint).
        assert s.get(m.Protocol, view.id) is not None
