"""Phase 6 Group 5: kiểm tra slice huấn luyện, thứ tự lưới (plan task 24, 24a)."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from backend.app.db import models as m

from .test_experiment_api import Api, Fx, _body, _create, _error, _post, api, env, fx, world
from .test_worker_services import _attack

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
