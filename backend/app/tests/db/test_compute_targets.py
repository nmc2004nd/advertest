"""Service compute_targets và audit (validation.md Phase 3: xác thực worker, kiểm toán)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from advertest_contracts.enums import BillingMode, ComputeKind, Role
from backend.app.db import models as m
from backend.app.services import audit, compute_targets
from backend.app.services.errors import Conflict, Forbidden, Invalid, NotFound

from .conftest import make_user

pytestmark = pytest.mark.db


def _name() -> str:
    return f"t-{uuid.uuid4().hex[:8]}"


def _audit(db: Session, entity_id: uuid.UUID) -> list[m.AuditLog]:
    return list(
        db.scalars(
            select(m.AuditLog)
            .where(m.AuditLog.entity_id == entity_id)
            .order_by(m.AuditLog.created_at)
        )
    )


def test_create_stores_only_token_hash(db: Session, admin: m.User) -> None:
    issued = compute_targets.create(db, actor=admin, name=_name(), gpu_model="RTX 3050")
    target = issued.target
    assert issued.token and target.token_hash == compute_targets.hash_token(issued.token)
    assert issued.token not in (target.token_hash or "")
    stored: str = db.execute(
        text("SELECT token_hash FROM compute_targets WHERE id = :id"), {"id": target.id}
    ).scalar_one()
    assert stored != issued.token and len(stored) == 64
    assert target.default_time_limit_s == 7200
    assert compute_targets.authenticate(db, issued.token) is target
    assert compute_targets.authenticate(db, "sai") is None
    assert compute_targets.authenticate(db, "") is None
    (row,) = _audit(db, target.id)
    assert (row.actor_id, row.action, row.entity_type) == (
        admin.id,
        "compute_target.create",
        "compute_target",
    )
    assert issued.token not in str(row.after)


def test_rotate_invalidates_old_token(db: Session, admin: m.User) -> None:
    name = _name()
    old = compute_targets.create(db, actor=admin, name=name)
    new = compute_targets.rotate_token(db, actor=admin, name=name)
    assert new.token != old.token
    assert compute_targets.authenticate(db, old.token) is None
    assert compute_targets.authenticate(db, new.token) is new.target
    assert [r.action for r in _audit(db, new.target.id)] == [
        "compute_target.create",
        "compute_target.rotate_token",
    ]
    with pytest.raises(NotFound):
        compute_targets.rotate_token(db, actor=admin, name="khong-co")


def test_create_rejects_non_local_and_duplicates(db: Session, admin: m.User) -> None:
    name = _name()
    with pytest.raises(Invalid):
        compute_targets.create(db, actor=admin, name=name, kind=ComputeKind.RENTED)
    with pytest.raises(Invalid):
        compute_targets.create(db, actor=admin, name=name, billing_mode=BillingMode.HOURLY)
    with pytest.raises(Invalid):
        compute_targets.create(db, actor=admin, name=name, time_limit_s=0)
    compute_targets.create(db, actor=admin, name=name)
    with pytest.raises(Conflict):
        compute_targets.create(db, actor=admin, name=name)


def test_require_admin(db: Session) -> None:
    admin = make_user(db)
    assert audit.require_admin(db, admin.email.upper()) is admin
    engineer = make_user(db, role=Role.ENGINEER)
    pending = make_user(db, active=False)
    for email in (engineer.email, pending.email, "khong-co@x.test"):
        with pytest.raises(Forbidden):
            audit.require_admin(db, email)
