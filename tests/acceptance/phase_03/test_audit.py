"""Kiểm toán (validation.md Phase 3, test_audit.py): CLI advertest-admin."""

from __future__ import annotations

import uuid

import pytest
import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from advertest_contracts.enums import Role, UserStatus
from backend.app.db import models as m

from .conftest import ADMIN, Harness, admin

pytestmark = pytest.mark.db


def _rows(harness: Harness, entity_id: uuid.UUID) -> list[tuple[str, str, str]]:
    with Session(harness.app_engine) as session:
        rows = session.execute(
            select(m.AuditLog.action, m.AuditLog.entity_type, m.User.email)
            .join(m.User, m.User.id == m.AuditLog.actor_id)
            .where(m.AuditLog.entity_id == entity_id)
            .order_by(m.AuditLog.created_at)
        ).all()
        return [(a, e, u) for a, e, u in rows]


def test_audit_rows_for_target_and_experiment_actions(harness: Harness) -> None:
    name, _ = harness.target()
    admin(harness.cli_env, "compute-target", "rotate-token", name, "--as", ADMIN)
    with Session(harness.app_engine) as session:
        target_id = session.query(m.ComputeTarget).filter_by(name=name).one().id
    assert _rows(harness, target_id) == [
        ("compute_target.create", "compute_target", ADMIN),
        ("compute_target.rotate_token", "compute_target", ADMIN),
    ]
    experiment_id = harness.submit(name, harness.world.config({"fgsm": [4]}))
    admin(harness.cli_env, "experiment", "cancel", str(experiment_id), "--as", ADMIN)
    assert _rows(harness, experiment_id) == [
        ("experiment.submit", "experiment", ADMIN),
        ("experiment.cancel", "experiment", ADMIN),
    ]


@pytest.mark.parametrize("kind", ["engineer", "pending_admin", "unknown"])
def test_as_non_active_admin_rejected(harness: Harness, kind: str) -> None:
    email = f"{kind}-{uuid.uuid4().hex[:6]}@example.com"
    if kind != "unknown":
        with Session(harness.app_engine) as session, session.begin():
            user = m.User(
                email=email, full_name="U", password_hash="x",
                status=UserStatus.ACTIVE if kind == "engineer" else UserStatus.PENDING,
            )  # fmt: skip
            session.add(user)
            session.flush()
            role = Role.ENGINEER if kind == "engineer" else Role.ADMIN
            session.add(m.UserRole(user_id=user.id, role=role))
    config = harness.tmp / "audit.yaml"
    config.write_text(yaml.safe_dump(harness.world.config({"fgsm": [4]})))
    name, _ = harness.target()
    commands = [
        ["compute-target", "create", "--name", f"x-{uuid.uuid4().hex[:6]}"],
        ["compute-target", "rotate-token", name],
        ["submit", "--config", str(config), "--target", name],
        ["import-local", "--store", str(harness.world.store_dir)],
    ]
    for args in commands:
        result = admin(harness.cli_env, *args, "--as", email, code=1)
        assert "Lỗi" in result.output
