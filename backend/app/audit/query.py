"""Đọc audit log cho admin (requirements.md Phase 4: lọc theo actor, action, entity, khoảng
thời gian; phân trang theo cursor; `actor` dạng object)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from advertest_contracts.models import AuditActor, AuditLogEntry, AuditLogPage
from backend.app.api import pagination
from backend.app.db import models as m
from backend.app.services.errors import Invalid


@dataclass(frozen=True)
class AuditFilter:
    actor_id: UUID | None = None
    action: str | None = None
    entity_type: str | None = None
    entity_id: UUID | None = None
    since: datetime | None = None  # gồm mốc
    until: datetime | None = None  # không gồm mốc


def _require_tz(value: datetime | None, name: str) -> None:
    if value is not None and value.tzinfo is None:
        raise Invalid(f"{name} phải có múi giờ (UTC)")


def list_entries(
    session: Session, filters: AuditFilter, *, cursor: str | None, limit: int
) -> AuditLogPage:
    _require_tz(filters.since, "since")
    _require_tz(filters.until, "until")
    query = select(m.AuditLog, m.User).outerjoin(m.User, m.User.id == m.AuditLog.actor_id)
    if filters.actor_id is not None:
        query = query.where(m.AuditLog.actor_id == filters.actor_id)
    if filters.action is not None:
        query = query.where(m.AuditLog.action == filters.action)
    if filters.entity_type is not None:
        query = query.where(m.AuditLog.entity_type == filters.entity_type)
    if filters.entity_id is not None:
        query = query.where(m.AuditLog.entity_id == filters.entity_id)
    if filters.since is not None:
        query = query.where(m.AuditLog.created_at >= filters.since)
    if filters.until is not None:
        query = query.where(m.AuditLog.created_at < filters.until)
    rows = list(
        session.execute(
            pagination.apply(
                query, m.AuditLog.created_at, m.AuditLog.id, pagination.decode(cursor), limit
            )
        )
    )
    page, more = rows[:limit], len(rows) > limit
    items = [
        AuditLogEntry(
            id=entry.id,
            actor=AuditActor(id=actor.id, full_name=actor.full_name, email=actor.email)
            if actor is not None
            else None,
            action=entry.action,
            entity_type=entry.entity_type,
            entity_id=entry.entity_id,
            before=entry.before,
            after=entry.after,
            created_at=entry.created_at.astimezone(UTC),
        )
        for entry, actor in page
    ]
    last = page[-1][0] if page else None
    return AuditLogPage(
        items=items,
        next_cursor=pagination.encode(last.created_at, last.id) if more and last else None,
    )
