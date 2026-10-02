"""validation.md Phase 8, Tuân thủ khi tạo (`test_compliance.py`)."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from sqlalchemy import Engine, delete, insert

from advertest_contracts.models import AttackSpec, compute_spec_sha256
from attacks.registry import get_spec, load_catalog
from backend.app.db import models as m

from .conftest import (
    LEVELS,
    P5,
    Flow,
    error,
    max_drop,
    ok,
    post,
    protocol_body,
    required_grid,
    unique,
)

pytestmark = pytest.mark.db


def _unsatisfied(response: httpx.Response) -> set[str]:
    assert response.status_code == 422, response.text
    body = response.json()["error"]
    assert body["code"] == "not_compliant", body
    return {item["code"] for item in body["compliance"] if not item["satisfied"]}


def _create(flow: Flow, attacks: list[dict[str, Any]], **changes: Any) -> httpx.Response:
    body = flow.api.body(flow.target, attacks, protocol_id=flow.protocol["id"], **changes)
    response: httpx.Response = post(flow.owner, "/experiments", body)
    return response


def _protocol(flow: Flow, **changes: Any) -> dict[str, Any]:
    body = protocol_body(**changes)
    created: dict[str, Any] = ok(
        post(flow.reviewer, "/protocols", {"name": unique("p"), "body": body})
    ).json()
    return created


def _search(name: str, **changes: Any) -> dict[str, Any]:
    spec = get_spec(load_catalog(), name=name)
    search = {
        "threshold_kind": "relative_drop",
        "threshold": 0.5,
        "class_filter": None,
        "lo": 0.0,
        "hi": 16.0,
        "max_tol": 2.0,
        "min_bootstrap_samples": 50,
    }
    search.update(changes)
    return {
        "attack_spec_name": name,
        "spec_sha256": spec.spec_sha256,
        "mode": "search",
        "search": search,
    }


def _search_attack(name: str, **changes: Any) -> dict[str, Any]:
    """Cấu hình tìm ngưỡng của experiment khớp `_search` (thay đổi qua `changes`)."""
    spec = get_spec(load_catalog(), name=name)
    search: dict[str, Any] = {
        "threshold_kind": "relative_drop",
        "threshold": 0.5,
        "class_filter": None,
        "lo": 0.0,
        "hi": 16.0,
        "tol": 2.0,
        "coarse_n": 3,
        "subset_size": 3,
        "bootstrap_samples": 50,
    }
    search.update(changes)
    return {
        "attack_spec_id": str(spec.id),
        "spec_sha256": spec.spec_sha256,
        "mode": "search",
        "search": search,
        "seed": 0,
    }


def test_missing_required_attack(flow: Flow) -> None:
    assert "attack_present" in _unsatisfied(_create(flow, [P5.attack("pgd_linf", [2.0])]))


def test_wrong_mode(flow: Flow) -> None:
    assert "mode" in _unsatisfied(_create(flow, [_search_attack("fgsm")]))


@pytest.fixture
def fgsm_v2(owner_engine: Engine) -> Iterator[AttackSpec]:
    """Catalog có thêm FGSM version mới (spec khác, hash khác); xóa khi test xong."""
    v1 = get_spec(load_catalog(), name="fgsm")
    body = v1.model_dump(mode="json", exclude={"id", "spec_sha256"})
    body.update(version=v1.version + 1)  # hash đổi theo version
    v2 = AttackSpec.model_validate(
        {**body, "id": str(uuid.uuid4()), "spec_sha256": compute_spec_sha256(body)}
    )
    with owner_engine.begin() as conn:
        conn.execute(
            insert(m.AttackSpecRow).values(
                id=v2.id,
                name=v2.name,
                version=v2.version,
                kind=v2.kind,
                access=v2.access,
                spec=v2.model_dump(mode="json"),
                spec_sha256=v2.spec_sha256,
            )
        )
    yield v2
    with owner_engine.begin() as conn:
        conn.execute(delete(m.AttackSpecRow).where(m.AttackSpecRow.id == v2.id))


def test_wrong_spec_sha256(flow: Flow, fgsm_v2: AttackSpec) -> None:
    attack = {
        "attack_spec_id": str(fgsm_v2.id),
        "spec_sha256": fgsm_v2.spec_sha256,
        "mode": "grid",
        "grid": {"levels": LEVELS},
        "seed": 0,
    }
    assert "spec_sha256" in _unsatisfied(_create(flow, [attack]))


def test_grid_levels_missing_or_extra(flow: Flow) -> None:
    assert "grid_levels" in _unsatisfied(_create(flow, [P5.attack("fgsm", [2.0])]))
    # Thêm level ngoài protocol: cho phép (chỉ tạo, không chạy).
    created = _create(flow, [P5.attack("fgsm", [2.0, 4.0, 8.0])])
    assert created.status_code == 201, created.text


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"threshold": 0.4}, "search_threshold"),
        ({"lo": 1.0}, "search_range"),
        ({"hi": 12.0}, "search_range"),
        ({"tol": 4.0}, "search_tol"),
        ({"bootstrap_samples": 20}, "search_bootstrap"),
    ],
)
def test_search_requirements(flow: Flow, changes: dict[str, Any], code: str) -> None:
    protocol = _protocol(
        flow,
        required_attacks=[_search("fgsm")],
        pass_criteria=[
            {
                "kind": "min_breaking_point",
                "attack_spec_name": "fgsm",
                "level": 4.0,
                "threshold_kind": "relative_drop",
                "threshold": 0.5,
                "class_filter": None,
            }
        ],
    )
    body = flow.api.body(
        flow.target, [_search_attack("fgsm", **changes)], protocol_id=protocol["id"]
    )
    assert code in _unsatisfied(post(flow.owner, "/experiments", body))
    # Đúng cấu hình protocol: tạo được.
    exact = flow.api.body(flow.target, [_search_attack("fgsm")], protocol_id=protocol["id"])
    assert post(flow.owner, "/experiments", exact).status_code == 201


def test_protocol_over_max_runs(flow: Flow) -> None:
    """Bốn attack quét lưới 12 level (48 run) cộng fog 3 level = 51 > `MAX_RUNS = 50`: không
    experiment nào tuân thủ được → 422; fog 2 level (đúng 50) thì tạo được."""
    twelve = [float(x) for x in range(1, 13)]

    def body(fog_levels: int) -> dict[str, Any]:
        return protocol_body(
            required_attacks=[
                required_grid("fgsm", twelve),
                required_grid("pgd_linf", twelve),
                required_grid("pgd_l2", twelve),
                required_grid("bbox_occlusion", [round(0.05 * k, 2) for k in range(1, 13)]),
                required_grid("fog", [float(x) for x in range(1, fog_levels + 1)]),
            ],
            pass_criteria=[max_drop("fgsm", 1.0)],
        )

    over = post(flow.reviewer, "/protocols", {"name": unique("p"), "body": body(3)})
    status, _, paths = error(over)
    assert status == 422 and paths == ["body.required_attacks"], over.text
    fits = post(flow.reviewer, "/protocols", {"name": unique("p"), "body": body(2)})
    assert fits.status_code == 201, fits.text


def test_slice_smaller_than_min(flow: Flow) -> None:
    protocol = _protocol(flow, min_slice_size=300)
    body = flow.api.body(flow.target, [P5.attack("fgsm", LEVELS)], protocol_id=protocol["id"])
    assert "min_slice_size" in _unsatisfied(post(flow.owner, "/experiments", body))


def test_model_without_gradients(flow: Flow) -> None:
    body = flow.api.body(
        flow.target,
        [P5.attack("fgsm", LEVELS)],
        gradient=False,
        protocol_id=flow.protocol["id"],
    )
    assert "model_gradients" in _unsatisfied(post(flow.owner, "/experiments", body))


@pytest.mark.parametrize(
    "attacks",
    [[P5.attack("fgsm", LEVELS)], [P5.attack("fgsm", [2.0])], [P5.attack("pgd_linf", [2.0])]],
    ids=["compliant", "missing-level", "missing-attack"],
)
def test_estimate_compliance_matches_creation(flow: Flow, attacks: list[dict[str, Any]]) -> None:
    body = flow.api.body(flow.target, attacks, protocol_id=flow.protocol["id"])
    estimate = ok(post(flow.owner, "/experiments/estimate", body)).json()
    created = post(flow.owner, "/experiments", body)
    if created.status_code == 201:
        assert all(item["satisfied"] for item in estimate["compliance"])
        return
    status, code, _ = error(created)
    assert (status, code) == (422, "not_compliant")

    # Bản tạo có thêm mục `protocol_active`; các mục còn lại giống ước lượng.
    # Bỏ trường null trước khi so: lỗi 422 tuần tự hóa không kèm trường null (exclude_none).
    def items(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {k: v for k, v in i.items() if v is not None}
            for i in raw
            if i["code"] != "protocol_active"
        ]

    from_create = items(created.json()["error"]["compliance"])
    from_estimate = items(estimate["compliance"])
    assert from_create == from_estimate
