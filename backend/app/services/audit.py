"""Audit log (chỉ thêm) và kiểm tra actor của CLI quản trị (`--as <email>`)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from advertest_contracts.enums import Role, UserStatus
from backend.app.db import models as m
from backend.app.services.errors import Forbidden


def require_admin(session: Session, email: str) -> m.User:
    """Người dùng `email` phải là admin `active` (requirements.md Phase 3, CLI quản trị)."""
    user = session.scalar(select(m.User).where(m.User.email == email.strip().lower()))
    if user is None or user.status != UserStatus.ACTIVE:
        raise Forbidden(f"{email} không phải tài khoản active")
    is_admin = session.scalar(
        select(m.UserRole).where(m.UserRole.user_id == user.id, m.UserRole.role == Role.ADMIN)
    )
    if is_admin is None:
        raise Forbidden(f"{email} không có role admin")
    return user


def record(
    session: Session,
    *,
    actor: m.User | None,
    action: str,
    entity_type: str,
    entity_id: UUID | None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    session.add(
        m.AuditLog(
            actor_id=actor.id if actor is not None else None,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            before=before,
            after=after,
        )
    )
