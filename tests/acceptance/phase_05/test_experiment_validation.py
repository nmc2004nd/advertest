"""validation.md Phase 5, Kiểm tra cấu hình (`test_experiment_validation.py`)."""

from __future__ import annotations

import json
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from advertest_contracts.enums import (
    AttackAccess,
    AttackKind,
    BillingMode,
    ComputeKind,
    ProtocolStatus,
)
from advertest_contracts.models import compute_spec_sha256
from backend.app.db import models as m

from .conftest import REPO, Api, attack, error, ok, post

pytestmark = pytest.mark.db


def _spec_copies(engine: Engine, count: int) -> list[dict[str, object]]:
    """Bản sao fgsm (tên khác) để có hơn 50 run hợp lệ (catalog chỉ có 3 attack)."""
    base = next(
        s for s in json.loads((REPO / "contracts" / "seeds" / "attack_specs.json").read_text())
        if s["name"] == "fgsm"
    )  # fmt: skip
    out: list[dict[str, object]] = []
    with Session(engine) as session, session.begin():
        for _ in range(count):
            body = {k: v for k, v in base.items() if k not in ("id", "spec_sha256")}
            body["name"] = f"fgsm_{uuid.uuid4().hex[:8]}"
            sha = compute_spec_sha256(body)
            row = m.AttackSpecRow(
                name=body["name"], version=1, kind=AttackKind.ATTACK,
                access=AttackAccess.WHITE_BOX, spec=body, spec_sha256=sha,
            )  # fmt: skip
            session.add(row)
            session.flush()
            out.append({"attack_spec_id": str(row.id), "spec_sha256": sha})
    return out


def test_no_attack(api: Api) -> None:
    _, _, client = api.user("engineer")
    body = api.body(api.target(), [])
    assert error(post(client, "/experiments", body)) == (422, "validation_error", ["attacks"])


def test_spec_hash_not_current(api: Api) -> None:
    _, _, client = api.user("engineer")
    stale = {**attack("fgsm", [4]), "spec_sha256": "0" * 64}
    status, _, paths = error(post(client, "/experiments", api.body(api.target(), [stale])))
    assert (status, paths) == (422, ["attacks.0.spec_sha256"])


@pytest.mark.parametrize(
    "levels",
    [[4, 99], [4, 4], [float(i) for i in range(1, 14)]],
    ids=["ngoai-dai", "trung", "hon-12"],
)
def test_level_rules(api: Api, levels: list[float]) -> None:
    _, _, client = api.user("engineer")
    body = api.body(api.target(), [attack("fgsm", levels)])
    assert error(post(client, "/experiments", body)) == (
        422, "invalid_request", ["attacks.0.grid.levels"],
    )  # fmt: skip


def test_more_than_50_runs(api: Api, app_engine: Engine) -> None:
    _, _, client = api.user("engineer")
    levels = [float(i) for i in range(1, 12)]  # 11 level, 5 attack: 55 run
    extra = [
        {**c, "mode": "grid", "grid": {"levels": levels}, "seed": 0}
        for c in _spec_copies(app_engine, 3)
    ]
    body = api.body(api.target(), [attack("fgsm", levels), attack("pgd_linf", levels), *extra])
    assert error(post(client, "/experiments", body)) == (422, "invalid_request", ["attacks"])


def test_search_mode_not_supported_yet(api: Api) -> None:
    # Phase 7 thu hẹp `not_supported_yet` của `mode = search` lại chỉ còn spec cần train patch
    # (requirements.md Phase 7, mục Context); kiểm tra theo `adv_patch`.
    _, _, client = api.user("engineer")
    search = {
        "threshold_kind": "relative_drop", "threshold": 0.2, "lo": 0.02, "hi": 0.25, "tol": 0.01,
        "coarse_n": 4, "subset_size": 2,
    }  # fmt: skip
    body = api.body(
        api.target(),
        [{**attack("adv_patch", [0.1]), "mode": "search", "grid": None, "search": search}],
    )
    assert error(post(client, "/experiments", body))[:2] == (422, "not_supported_yet")


def test_slice_and_mapping_must_match(api: Api) -> None:
    _, _, client = api.user("engineer")
    target = api.target()
    wrong_model = api.body(
        target, [attack("fgsm", [4])], class_mapping_id=api.world.random_mapping_id
    )
    assert error(post(client, "/experiments", wrong_model))[2] == ["class_mapping_id"]
    unknown_slice = api.body(target, [attack("fgsm", [4])], slice_id=str(uuid.uuid4()))
    assert error(post(client, "/experiments", unknown_slice))[2] == ["slice_id"]


def test_retired_protocol(api: Api, app_engine: Engine) -> None:
    with Session(app_engine) as session, session.begin():
        admin = session.query(m.User).filter_by(email="admin-phase05@example.com").one()
        protocol = m.Protocol(
            name=f"cu-{uuid.uuid4().hex[:6]}", version=1, body={}, body_sha256="a" * 64,
            status=ProtocolStatus.RETIRED, created_by=admin.id,
        )  # fmt: skip
        session.add(protocol)
        session.flush()
        protocol_id = str(protocol.id)
    _, _, client = api.user("engineer")
    body = api.body(api.target(), [attack("fgsm", [4])], protocol_id=protocol_id)
    assert error(post(client, "/experiments", body))[2] == ["protocol_id"]


def test_target_and_limit_rules(api: Api, app_engine: Engine) -> None:
    with Session(app_engine) as session, session.begin():
        rented = m.ComputeTarget(
            name=f"thue-{uuid.uuid4().hex[:6]}", kind=ComputeKind.RENTED,
            billing_mode=BillingMode.HOURLY, price_per_hour=Decimal("2"), currency="USD",
        )  # fmt: skip
        session.add(rented)
        session.flush()
        rented_id = str(rented.id)
    _, _, client = api.user("engineer")
    target = api.target()
    fgsm = [attack("fgsm", [4])]
    cases = {
        "compute_target_id": api.body(target, fgsm, compute_target_id=rented_id),
        "limit.kind": api.body(target, fgsm, limit={"kind": "budget", "value": "5"}),
        "limit.value": api.body(target, fgsm, limit={"kind": "time", "value": "28801"}),
    }
    for path, body in cases.items():
        assert error(post(client, "/experiments", body)) == (422, "invalid_request", [path]), path


def test_fourth_queued_experiment_of_same_user(api: Api) -> None:
    _, _, client = api.user("engineer")
    target = api.target()
    body = api.body(target, [attack("fgsm", [4])])
    for _ in range(3):
        ok(post(client, "/experiments", body))
    assert error(post(client, "/experiments", body))[:2] == (409, "queue_limit_reached")
    _, _, other = api.user("engineer")
    ok(post(other, "/experiments", body))  # người khác không bị ảnh hưởng


def test_estimate_and_create_give_same_validation(api: Api) -> None:
    _, _, client = api.user("engineer")
    body = api.body(
        api.target(),
        [attack("fgsm", [99]), {**attack("pgd_linf", [4]), "spec_sha256": "1" * 64}],
        limit={"kind": "time", "value": "99999"},
    )
    estimate = error(post(client, "/experiments/estimate", body))
    create = error(post(client, "/experiments", body))
    assert estimate == create
    assert create[2] == ["attacks.0.grid.levels", "attacks.1.spec_sha256", "limit.value"]
