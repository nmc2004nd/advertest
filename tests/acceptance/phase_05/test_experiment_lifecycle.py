"""validation.md Phase 5, Quyền và vòng đời (`test_experiment_lifecycle.py`). Worker thật (CPU)."""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Sequence
from uuid import UUID

import pytest
from sqlalchemy import Engine, func, select, update
from sqlalchemy.orm import Session

from advertest_contracts.enums import AttackAccess, AttackKind
from advertest_contracts.models import (
    ExperimentClone,
    ExperimentDetail,
    RunView,
    compute_spec_sha256,
)
from backend.app.db import models as m

from .conftest import REPO, Api, attack, error, ok, post

pytestmark = pytest.mark.db


def _audit(engine: Engine, experiment_id: str, action: str) -> int:
    with Session(engine) as session:
        return (
            session.scalar(
                select(func.count())
                .select_from(m.AuditLog)
                .where(m.AuditLog.entity_id == UUID(experiment_id), m.AuditLog.action == action)
            )
            or 0
        )


def test_create_then_worker_completes(api: Api, app_engine: Engine) -> None:
    target = api.target()
    api.profile(target, sec=0.05, batch=5, attacks=["fgsm"])
    _, _, client = api.user("engineer")
    created = ExperimentDetail.model_validate(
        ok(post(client, "/experiments", api.body(target, [attack("fgsm", [4])]))).json()
    )
    assert created.status == "queued" and created.finished_at is None
    assert _audit(app_engine, str(created.id), "experiment.submit") == 1

    api.clock.advance(60)
    api.work(target, str(created.id))
    detail = ExperimentDetail.model_validate(client.get(f"/experiments/{created.id}").json())
    assert detail.status == "completed"
    assert detail.finished_at == api.clock.now
    (run,) = [
        RunView.model_validate(r) for r in client.get(f"/experiments/{created.id}/runs").json()
    ]
    assert run.status == "completed" and run.fingerprint is not None and run.metrics is not None


def test_reviewer_and_admin_cannot_create(api: Api) -> None:
    body = api.body(api.target(), [attack("fgsm", [4])])
    for role in ("reviewer", "admin"):
        _, _, client = api.user(role)
        assert error(post(client, "/experiments", body))[:2] == (403, "forbidden")


def test_every_active_user_reads_others_experiments(api: Api) -> None:
    _, _, owner = api.user("engineer")
    created = ok(post(owner, "/experiments", api.body(api.target(), [attack("fgsm", [4])]))).json()
    for role in ("engineer", "reviewer", "admin"):
        _, _, other = api.user(role)
        assert other.get(f"/experiments/{created['id']}").status_code == 200
        assert other.get(f"/experiments/{created['id']}/runs").status_code == 200


def test_cancel_rules_and_worker_stops(api: Api, app_engine: Engine) -> None:
    target = api.target()
    api.profile(target, sec=0.05, batch=1, attacks=["fgsm"])  # 1 ảnh mỗi batch
    _, _, owner = api.user("engineer")
    created = ok(post(owner, "/experiments", api.body(target, [attack("fgsm", [4, 8])]))).json()
    experiment_id = created["id"]
    _, _, other = api.user("engineer")
    assert error(post(other, f"/experiments/{experiment_id}/cancel"))[:2] == (403, "forbidden")

    processed: list[str] = []

    def cancel_after_first_batch(_run_id: UUID, ids: Sequence[str]) -> None:
        processed.extend(ids)
        if len(processed) == 1:
            detail = ok(post(owner, f"/experiments/{experiment_id}/cancel")).json()
            assert detail["status"] == "cancelled"
            time.sleep(0.5)  # luồng heartbeat nhận chỉ thị cancel

    api.work(target, experiment_id, on_batch=cancel_after_first_batch, heartbeat=0.1)
    detail = ExperimentDetail.model_validate(owner.get(f"/experiments/{experiment_id}").json())
    assert detail.status == "cancelled" and detail.finished_at is not None
    assert detail.run_counts.cancelled == 2
    assert len(processed) == 1  # worker dừng sau batch hiện tại
    assert _audit(app_engine, experiment_id, "experiment.cancel") == 1


def test_cancel_completed_is_conflict(api: Api) -> None:
    target = api.target()
    api.profile(target, sec=0.05, batch=5, attacks=["fgsm"])
    _, _, owner = api.user("engineer")
    created = ok(post(owner, "/experiments", api.body(target, [attack("fgsm", [2])]))).json()
    api.work(target, created["id"])
    assert error(post(owner, f"/experiments/{created['id']}/cancel"))[:2] == (409, "conflict")


def test_clone_same_config_then_new_spec_version(api: Api, app_engine: Engine) -> None:
    base = next(
        s for s in json.loads((REPO / "contracts" / "seeds" / "attack_specs.json").read_text())
        if s["name"] == "fgsm"
    )  # fmt: skip
    name = f"fgsm_clone_{uuid.uuid4().hex[:6]}"

    def add_version(version: int) -> tuple[str, str]:
        body = {k: v for k, v in base.items() if k not in ("id", "spec_sha256")}
        body.update(name=name, version=version)
        sha = compute_spec_sha256(body)
        with Session(app_engine) as session, session.begin():
            row = m.AttackSpecRow(
                name=name, version=version, kind=AttackKind.ATTACK,
                access=AttackAccess.WHITE_BOX, spec=body, spec_sha256=sha,
            )  # fmt: skip
            session.add(row)
            session.flush()
            return str(row.id), sha

    v1_id, v1_sha = add_version(1)
    _, _, client = api.user("engineer")
    v1_attack = {"attack_spec_id": v1_id, "spec_sha256": v1_sha, "mode": "grid",
                 "grid": {"levels": [2, 4]}, "seed": 0}  # fmt: skip
    created = ok(post(client, "/experiments", api.body(api.target(), [v1_attack]))).json()

    same = ExperimentClone.model_validate(client.get(f"/experiments/{created['id']}/clone").json())
    assert same.warnings == []
    assert [a.model_dump(mode="json") for a in same.config.attacks] == created["config"]["attacks"]
    assert str(same.config.cloned_from) == created["id"]

    v2_id, _ = add_version(2)
    with Session(app_engine) as session, session.begin():
        session.execute(
            update(m.AttackSpecRow).where(m.AttackSpecRow.id == UUID(v1_id)).values(is_active=False)
        )
    updated = ExperimentClone.model_validate(
        client.get(f"/experiments/{created['id']}/clone").json()
    )
    assert str(updated.config.attacks[0].attack_spec_id) == v2_id
    assert [(w.from_version, w.to_version) for w in updated.warnings] == [(1, 2)]
