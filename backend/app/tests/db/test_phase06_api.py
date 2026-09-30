"""Phase 6 Group 5: kiểm tra slice huấn luyện, thứ tự lưới (plan task 24, 24a)."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from advertest_contracts.enums import Role
from attacks.registry import get_spec, load_catalog
from backend.app.db import models as m
from backend.app.services.patches import patch_key_for

from .test_experiment_api import (
    Api,
    Fx,
    _body,
    _create,
    _error,
    _estimate,
    _new_target,
    _post,
    api,
    env,
    fx,
    world,
)
from .test_worker_services import T0, _attack

pytestmark = pytest.mark.db
__all__ = ["api", "env", "fx", "world"]


def _training_slice(
    engine: Engine, fx: Fx, image_ids: list[str], *, registered: bool = True, same_dv: bool = True
) -> uuid.UUID:
    with Session(engine) as s, s.begin():
        evaluation = s.get(m.Slice, fx.slice)
        other = s.get(m.Slice, fx.other_slice)
        assert evaluation is not None and other is not None
        row = m.Slice(
            dataset_version_id=(
                evaluation.dataset_version_id if same_dv else other.dataset_version_id
            ),
            name=f"train-{uuid.uuid4().hex[:6]}",
            filter={},
            seed=0,
            image_ids=image_ids,
            image_ids_sha256=uuid.uuid4().hex * 2,
            slice_sha256=uuid.uuid4().hex * 2 if registered else None,
        )
        s.add(row)
        s.flush()
        return row.id


def _eval_ids(engine: Engine, fx: Fx) -> list[str]:
    with Session(engine) as s:
        row = s.get(m.Slice, fx.slice)
        assert row is not None
        return list(row.image_ids)


def _patch(levels: list[float], training: uuid.UUID | None) -> dict[str, Any]:
    attack = _attack("adv_patch", levels)
    if training is not None:
        attack["training_slice_id"] = str(training)
    return attack


def _fields(api: Api, fx: Fx, attacks: list[dict[str, Any]]) -> tuple[int, str, list[str]]:
    _, client = api.client()
    return _error(_post(client, "/experiments", _body(fx, attacks=attacks)))


def test_patch_needs_training_slice(api: Api, fx: Fx) -> None:
    assert _fields(api, fx, [_patch([0.1], None)]) == (
        422, "invalid_request", ["attacks.0.training_slice_id"],
    )  # fmt: skip


def test_training_slice_rules(api: Api, fx: Fx, owner_engine: Engine) -> None:
    evaluation = _eval_ids(owner_engine, fx)
    path = ["attacks.0.training_slice_id"]
    overlapping = _training_slice(owner_engine, fx, [evaluation[0], "x-1"])
    assert _fields(api, fx, [_patch([0.1], overlapping)])[2] == path
    other_dv = _training_slice(owner_engine, fx, ["x-2"], same_dv=False)
    assert _fields(api, fx, [_patch([0.1], other_dv)])[2] == path
    too_big = _training_slice(owner_engine, fx, [f"big-{i}" for i in range(51)])
    assert _fields(api, fx, [_patch([0.1], too_big)])[2] == path
    unregistered = _training_slice(owner_engine, fx, ["x-3"], registered=False)
    assert _fields(api, fx, [_patch([0.1], unregistered)])[2] == path
    assert _fields(api, fx, [_patch([0.1], uuid.uuid4())])[2] == path
    fgsm = {**_attack("fgsm", [4]), "training_slice_id": str(overlapping)}
    assert _fields(api, fx, [fgsm])[2] == path


def test_valid_patch_and_coarse_to_fine_order(api: Api, fx: Fx, owner_engine: Engine) -> None:
    training = _training_slice(owner_engine, fx, ["t-1", "t-2"])
    _, client = api.client()
    body = _body(fx, attacks=[_attack("fgsm", [2, 4, 8, 16, 32]), _patch([0.1, 0.25], training)])
    detail = _create(client, body)
    runs = client.get(f"/experiments/{detail.id}/runs").json()
    assert [r["level"] for r in runs] == [2, 8, 32, 4, 16, 0.1, 0.25]


def test_slices_disjoint_from(api: Api, fx: Fx, owner_engine: Engine) -> None:
    """Plan task 24b."""
    evaluation = _eval_ids(owner_engine, fx)
    disjoint = _training_slice(owner_engine, fx, ["d-1"])
    overlapping = _training_slice(owner_engine, fx, [evaluation[0]])
    _, client = api.client()
    ids = {s["id"] for s in client.get(f"/slices?disjoint_from={fx.slice}").json()}
    assert str(disjoint) in ids and str(overlapping) not in ids and str(fx.slice) not in ids
    assert client.get(f"/slices?disjoint_from={uuid.uuid4()}").status_code == 404


def _patch_profile(owner_engine: Engine, fx: Fx, target: uuid.UUID, spi: float | None) -> None:
    spec = get_spec(load_catalog(), name="adv_patch")
    with Session(owner_engine) as s, s.begin():
        s.add(
            m.CostProfile(
                compute_target_id=target, model_version_id=fx.model, attack_spec_id=spec.id,
                sec_per_image=0.5, peak_vram_mb=0, batch_size=2, measured_at=T0,
                sec_per_image_iteration=spi,
            )
        )  # fmt: skip


def test_estimate_training_seconds(api: Api, fx: Fx, owner_engine: Engine) -> None:
    """Plan task 25: `max_iter * số ảnh * sec_per_image_iteration`, cộng vào tổng và giới hạn;
    patch đã đăng ký thì không train."""
    target = _new_target(owner_engine)
    _patch_profile(owner_engine, fx, target, 0.25)
    training = _training_slice(owner_engine, fx, ["e-1", "e-2"])
    _, client = api.client()
    body = _body(fx, [_patch([0.1, 0.25], training)], compute_target_id=str(target))
    result = _estimate(client, body)
    spec = get_spec(load_catalog(), name="adv_patch")
    assert spec.training is not None
    train = spec.training.max_iter * 2 * 0.25
    assert [r.training_seconds for r in result.runs] == [train, train]
    evaluation = sum(r.est_seconds or 0 for r in result.runs)
    assert result.total_seconds == pytest.approx(evaluation + 2 * train)

    limited = {**body, "limit": {"kind": "time", "value": str(int(evaluation) + 1)}}
    assert _estimate(client, limited).exceeds_limit is True  # chỉ vượt nhờ phần train

    # Patch 0.1 đã đăng ký: không train lại.
    with Session(owner_engine) as s, s.begin():
        slice_row = s.get(m.Slice, training)
        model = s.get(m.ModelVersion, fx.model)
        assert slice_row is not None and slice_row.slice_sha256 and model is not None
        key = patch_key_for(spec, model.weights_sha256, slice_row.slice_sha256, 0.1, 0)
        s.add(m.Patch(key=key, attack_spec_id=spec.id, area_ratio=0.1, artifact={"key": key}))
    again = _estimate(client, body)
    assert [r.training_seconds for r in again.runs] == [None, train]


def test_estimate_without_training_cost(api: Api, fx: Fx, owner_engine: Engine) -> None:
    target = _new_target(owner_engine)
    _patch_profile(owner_engine, fx, target, None)
    training = _training_slice(owner_engine, fx, ["n-1"])
    _, client = api.client()
    result = _estimate(client, _body(fx, [_patch([0.1], training)], compute_target_id=str(target)))
    assert result.runs[0].training_seconds is None and result.total_seconds is not None


def test_admin_attack_catalog(api: Api, owner_engine: Engine) -> None:
    """Plan task 29: mọi spec kể cả spec đã tắt, phân trang; chỉ admin (validation Quyền)."""
    with Session(owner_engine) as s, s.begin():
        off = s.get(m.AttackSpecRow, get_spec(load_catalog(), name="fog").id)
        assert off is not None
        off.is_active = False
    try:
        _, admin = api.client(Role.ADMIN)
        seen: list[dict[str, Any]] = []
        cursor = None
        while True:
            query = "?limit=3" + (f"&cursor={cursor}" if cursor else "")
            response = admin.get(f"/admin/attack-specs{query}")
            assert response.status_code == 200, response.text
            page = response.json()
            seen += page["items"]
            cursor = page["next_cursor"]
            if cursor is None:
                break
        names = {item["name"] for item in seen}
        assert {s.name for s in load_catalog()} <= names
        assert len({item["id"] for item in seen}) == len(seen)  # không trùng giữa các trang
        fog = next(item for item in seen if item["name"] == "fog")
        assert fog["is_active"] is False
        for role in (Role.ENGINEER, Role.REVIEWER):
            _, other = api.client(role)
            assert other.get("/admin/attack-specs").status_code == 403
        assert admin.get("/admin/attack-specs?cursor=khong-hop-le").status_code == 422
    finally:
        with Session(owner_engine) as s, s.begin():
            row = s.get(m.AttackSpecRow, get_spec(load_catalog(), name="fog").id)
            assert row is not None
            row.is_active = True
