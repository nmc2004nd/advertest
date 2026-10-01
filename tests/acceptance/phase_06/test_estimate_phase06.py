"""validation.md Phase 6, Ước lượng (`test_estimate_phase06.py`)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from advertest_contracts.models import EstimateResponse, compute_patch_key
from backend.app.db import models as m

from .conftest import (
    PATCH_MAX_ITER,
    World6,
    grid_attack,
    ok,
    patch_attack,
    post,
    profile,
    spec_id,
)

pytestmark = pytest.mark.db
SPI = 0.25  # giây mỗi ảnh mỗi vòng train


def _estimate(client: Any, body: dict[str, Any]) -> EstimateResponse:
    return EstimateResponse.model_validate(ok(post(client, "/experiments/estimate", body)).json())


def test_training_seconds_until_patch_exists(api: Any, world: World6, owner_engine: Engine) -> None:
    target = api.target()
    profile(api, target, {world.patch.id: 0.5}, sec_per_image_iteration={world.patch.id: SPI})
    _, _, client = api.user("engineer")
    body = api.body(target, [patch_attack(world, [0.12, 0.22])])
    result = _estimate(client, body)
    train = PATCH_MAX_ITER * len(world.training_image_ids) * SPI
    assert [r.training_seconds for r in result.runs] == [pytest.approx(train)] * 2
    evaluation = sum(r.est_seconds or 0 for r in result.runs)
    assert result.total_seconds == pytest.approx(evaluation + 2 * train)
    # Chỉ vượt giới hạn nhờ phần train.
    limited = {**body, "limit": {"kind": "time", "value": str(int(evaluation) + 1)}}
    assert _estimate(client, limited).exceeds_limit is True

    # Patch 0.12 đã có: không train lại. (Khóa riêng của test: test_patch train khóa 0.1.)
    with Session(owner_engine) as session, session.begin():
        training = session.get(m.Slice, UUID(world.training_slice_id))
        model = session.get(m.ModelVersion, UUID(world.base.model_id))
        assert training is not None and training.slice_sha256 and model is not None
        key = compute_patch_key(
            spec_sha256=world.patch.spec_sha256, weights_sha256=model.weights_sha256,
            training_slice_sha256=training.slice_sha256, area_ratio=0.12, seed=0,
        )  # fmt: skip
        session.add(m.Patch(key=key, attack_spec_id=world.patch.id, area_ratio=0.12,
                            artifact={"key": key}))  # fmt: skip
    again = _estimate(client, body)
    assert [r.training_seconds for r in again.runs] == [None, pytest.approx(train)]


def test_calibration_of_new_specs(api: Any, world: World6, app_engine: Engine) -> None:
    """Không có cost profile: worker calibration cho spec mới (corruption, occlusion, patch) chạy
    được và experiment xong; profile của adv_patch có `sec_per_image_iteration`."""
    target = api.target()
    _, _, client = api.user("engineer")
    attacks = [grid_attack("fog", [1]), grid_attack("bbox_occlusion", [0.3]),
               patch_attack(world, [0.05])]  # fmt: skip
    created = ok(post(client, "/experiments", api.body(target, attacks))).json()
    api.work(target, created["id"])
    assert client.get(f"/experiments/{created['id']}").json()["status"] == "completed"
    runs = client.get(f"/experiments/{created['id']}/runs").json()
    assert {r["status"] for r in runs} == {"completed"}, runs
    with Session(app_engine) as session:
        rows = {
            row.attack_spec_id: row
            for row in session.scalars(
                select(m.CostProfile).where(m.CostProfile.compute_target_id == UUID(target.id))
            )
        }
    for name in ("fog", "bbox_occlusion"):
        assert rows[UUID(spec_id(name))].sec_per_image > 0, name
    patch = rows[world.patch.id]
    assert patch.sec_per_image > 0
    assert patch.sec_per_image_iteration is not None and patch.sec_per_image_iteration > 0
