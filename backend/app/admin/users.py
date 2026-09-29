"""Quản trị người dùng (requirements.md Phase 4, mục Luật quản trị).

Mỗi thao tác khóa dòng user (`FOR UPDATE`) và ghi `audit_log` với `before`/`after`
(`{status, roles}`) trong cùng transaction. Thao tác có thể làm mất admin `active` lấy thêm
advisory lock chung, để hai admin không cùng lúc hạ nhau.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.orm import Session

from advertest_contracts.enums import Role, UserStatus
from advertest_contracts.models import PasswordResetLink, UserAdminPage, UserAdminView
from backend.app.api import pagination
from backend.app.auth import sessions
from backend.app.auth.service import load_roles
from backend.app.db import models as m
from backend.app.services import audit
from backend.app.services.errors import Conflict, NotFound

RESET_LINK_TTL = timedelta(hours=24)
DEFAULT_APP_BASE_URL = "http://localhost:5173"
# Khóa advisory (transaction) cho mọi thao tác có thể làm giảm số admin active.
_ADMIN_LOCK_KEY = 0x41445649  # "ADVI"


def app_base_url() -> str:
    return os.environ.get("APP_BASE_URL", DEFAULT_APP_BASE_URL).rstrip("/")


def _state(user: m.User, roles: frozenset[Role]) -> dict[str, object]:
    return {"status": user.status.value, "roles": sorted(r.value for r in roles)}


def view(user: m.User, roles: frozenset[Role]) -> UserAdminView:
    return UserAdminView(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        organization=user.organization,
        status=user.status,
        roles=sorted(roles),
        requested_role=user.requested_role,
        request_reason=user.request_reason,
        reject_reason=user.reject_reason,
        # Contract đòi UTC; timestamptz trả về theo múi giờ của phiên Postgres.
        created_at=user.created_at.astimezone(UTC),
        approved_at=user.approved_at.astimezone(UTC) if user.approved_at else None,
        approved_by=user.approved_by,
    )


def _lock_user(session: Session, user_id: UUID) -> m.User:
    user = session.get(m.User, user_id, with_for_update=True)
    if user is None:
        raise NotFound("Không tìm thấy người dùng")
    return user


def _lock_admins(session: Session) -> None:
    session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _ADMIN_LOCK_KEY})


def _other_active_admins(session: Session, user_id: UUID) -> int:
    return (
        session.scalar(
            select(func.count())
            .select_from(m.User)
            .join(m.UserRole, m.UserRole.user_id == m.User.id)
            .where(
                m.UserRole.role == Role.ADMIN,
                m.User.status == UserStatus.ACTIVE,
                m.User.id != user_id,
            )
        )
        or 0
    )


def _require_status(user: m.User, *allowed: UserStatus, action: str) -> None:
    if user.status not in allowed:
        raise Conflict(f"Không thể {action} người dùng ở trạng thái {user.status.value}")


def _set_roles(session: Session, user_id: UUID, roles: list[Role]) -> None:
    session.execute(delete(m.UserRole).where(m.UserRole.user_id == user_id))
    session.add_all(m.UserRole(user_id=user_id, role=role) for role in roles)
    session.flush()


def _record(
    session: Session,
    actor: m.User,
    action: str,
    user: m.User,
    before: dict[str, object],
    after: dict[str, object],
) -> None:
    audit.record(
        session,
        actor=actor,
        action=action,
        entity_type="user",
        entity_id=user.id,
        before=before,
        after=after,
    )


def approve(
    session: Session, actor: m.User, user_id: UUID, roles: list[Role], *, now: datetime
) -> UserAdminView:
    user = _lock_user(session, user_id)
    _require_status(user, UserStatus.PENDING, action="duyệt")
    before = _state(user, load_roles(session, user.id))
    user.status = UserStatus.ACTIVE
    user.approved_at = now
    user.approved_by = actor.id
    user.reject_reason = None
    _set_roles(session, user.id, roles)
    after_roles = frozenset(roles)
    _record(session, actor, "user.approved", user, before, _state(user, after_roles))
    return view(user, after_roles)


def reject(session: Session, actor: m.User, user_id: UUID, reason: str) -> UserAdminView:
    user = _lock_user(session, user_id)
    _require_status(user, UserStatus.PENDING, action="từ chối")
    roles = load_roles(session, user.id)
    before = _state(user, roles)
    user.status = UserStatus.REJECTED
    user.reject_reason = reason
    session.flush()
    _record(session, actor, "user.rejected", user, before, _state(user, roles))
    return view(user, roles)


def update_roles(
    session: Session, actor: m.User, user_id: UUID, roles: list[Role]
) -> UserAdminView:
    _lock_admins(session)
    user = _lock_user(session, user_id)
    _require_status(user, UserStatus.ACTIVE, UserStatus.DISABLED, action="đổi role")
    current = load_roles(session, user.id)
    removes_admin = Role.ADMIN in current and Role.ADMIN not in roles
    if (
        removes_admin
        and user.status == UserStatus.ACTIVE
        and _other_active_admins(session, user.id) == 0
    ):
        raise Conflict("Không thể bỏ role admin của admin active cuối cùng")
    before = _state(user, current)
    _set_roles(session, user.id, roles)
    after_roles = frozenset(roles)
    _record(session, actor, "user.roles_changed", user, before, _state(user, after_roles))
    return view(user, after_roles)


def disable(session: Session, actor: m.User, user_id: UUID, *, now: datetime) -> UserAdminView:
    if user_id == actor.id:
        raise Conflict("Admin không thể tự vô hiệu hóa chính mình")
    _lock_admins(session)
    user = _lock_user(session, user_id)
    _require_status(user, UserStatus.ACTIVE, action="vô hiệu hóa")
    roles = load_roles(session, user.id)
    if Role.ADMIN in roles and _other_active_admins(session, user.id) == 0:
        raise Conflict("Không thể vô hiệu hóa admin active cuối cùng")
    before = _state(user, roles)
    user.status = UserStatus.DISABLED
    user.disabled_at = now
    sessions.revoke_all(session, user.id, now=now)
    session.flush()
    _record(session, actor, "user.disabled", user, before, _state(user, roles))
    return view(user, roles)


def enable(session: Session, actor: m.User, user_id: UUID) -> UserAdminView:
    user = _lock_user(session, user_id)
    _require_status(user, UserStatus.DISABLED, action="kích hoạt")
    roles = load_roles(session, user.id)
    before = _state(user, roles)
    user.status = UserStatus.ACTIVE
    user.disabled_at = None
    session.flush()
    _record(session, actor, "user.enabled", user, before, _state(user, roles))
    return view(user, roles)


def create_reset_link(
    session: Session, actor: m.User, user_id: UUID, *, now: datetime
) -> PasswordResetLink:
    """Link một lần, hết hạn sau 24 giờ; link cũ chưa dùng của user bị vô hiệu (người dùng chốt,
    Phase 4 Group 3). DB chỉ lưu sha256 của token; audit không ghi token."""
    user = _lock_user(session, user_id)
    _require_status(user, UserStatus.ACTIVE, UserStatus.DISABLED, action="tạo link đặt lại cho")
    session.execute(
        update(m.PasswordResetToken)
        .where(m.PasswordResetToken.user_id == user.id, m.PasswordResetToken.used_at.is_(None))
        .values(used_at=now)
    )
    token = sessions.new_token()
    expires_at = now + RESET_LINK_TTL
    session.add(
        m.PasswordResetToken(
            user_id=user.id,
            token_sha256=sessions.token_sha256(token),
            created_by=actor.id,
            created_at=now,
            expires_at=expires_at,
        )
    )
    state = _state(user, load_roles(session, user.id))
    _record(session, actor, "user.reset_link_created", user, state, state)
    return PasswordResetLink(url=f"{app_base_url()}/reset-password/{token}", expires_at=expires_at)


def get_actor(session: Session, actor_id: UUID) -> m.User:
    return session.get_one(m.User, actor_id)


def list_users(
    session: Session, *, status: UserStatus | None, cursor: str | None, limit: int
) -> UserAdminPage:
    query = select(m.User)
    if status is not None:
        query = query.where(m.User.status == status)
    rows = list(
        session.scalars(
            pagination.apply(query, m.User.created_at, m.User.id, pagination.decode(cursor), limit)
        )
    )
    page, more = rows[:limit], len(rows) > limit
    roles: dict[UUID, set[Role]] = {user.id: set() for user in page}
    for user_id, role in session.execute(
        select(m.UserRole.user_id, m.UserRole.role).where(m.UserRole.user_id.in_(roles))
    ):
        roles[user_id].add(role)
    return UserAdminPage(
        items=[view(user, frozenset(roles[user.id])) for user in page],
        next_cursor=pagination.encode(page[-1].created_at, page[-1].id) if more else None,
    )
