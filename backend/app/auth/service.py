"""Nghiệp vụ xác thực: yêu cầu truy cập, đăng nhập, đổi và đặt lại mật khẩu
(requirements.md Phase 4, bảng Endpoint và mục Phiên và bảo mật).

Hàm trả kết quả thay vì ném lỗi khi cần giữ lại thay đổi trong transaction (ví dụ sự kiện
`login_failed` phải được commit dù đăng nhập thất bại).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from advertest_contracts.enums import ErrorCode, Role, UserStatus
from advertest_contracts.models import (
    AccessRequest,
    LoginRequest,
    Me,
    PasswordChange,
    PasswordResetConsume,
)
from advertest_contracts.permissions import permissions_for
from backend.app.auth import passwords, rate_limit, sessions
from backend.app.db import models as m
from backend.app.services import audit

ACCOUNT_STATUS_ERRORS = {
    UserStatus.PENDING: ErrorCode.ACCOUNT_PENDING,
    UserStatus.REJECTED: ErrorCode.ACCOUNT_REJECTED,
    UserStatus.DISABLED: ErrorCode.ACCOUNT_DISABLED,
}


@dataclass(frozen=True)
class AuthFailure:
    code: ErrorCode
    message: str


def load_roles(session: Session, user_id: UUID) -> frozenset[Role]:
    return frozenset(session.scalars(select(m.UserRole.role).where(m.UserRole.user_id == user_id)))


def build_me(user: m.User, roles: frozenset[Role]) -> Me:
    return Me(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        roles=sorted(roles),
        permissions=sorted(permissions_for(roles)),
        status=user.status,
    )


def _state(status: UserStatus, roles: frozenset[Role]) -> dict[str, object]:
    return {"status": status.value, "roles": sorted(r.value for r in roles)}


def request_access(session: Session, body: AccessRequest) -> None:
    """Tạo user `pending`. Email đã tồn tại: không tạo gì, kết quả giống hệt (không lộ email).

    Luôn băm mật khẩu để thời gian phản hồi không phụ thuộc email đã tồn tại hay chưa.
    """
    password_hash = passwords.hash_password(body.password)
    user_id = session.scalar(
        insert(m.User)
        .values(
            email=body.email,
            full_name=body.full_name,
            organization=body.organization,
            password_hash=password_hash,
            status=UserStatus.PENDING,
            requested_role=body.requested_role,
            request_reason=body.reason,
        )
        .on_conflict_do_nothing(index_elements=["email"])
        .returning(m.User.id)
    )
    if user_id is None:
        return
    user = session.get_one(m.User, user_id)
    audit.record(
        session,
        actor=user,
        action="user.access_requested",
        entity_type="user",
        entity_id=user.id,
        after=_state(UserStatus.PENDING, frozenset()),
    )


@dataclass(frozen=True)
class LoginSuccess:
    me: Me
    issued: sessions.IssuedSession


def login(
    session: Session,
    body: LoginRequest,
    *,
    ip: str | None,
    user_agent: str | None,
    now: datetime,
) -> LoginSuccess | AuthFailure:
    if rate_limit.is_limited(session, email=body.email, ip=ip, now=now):
        return AuthFailure(ErrorCode.RATE_LIMITED, "Đăng nhập sai quá nhiều lần, thử lại sau")
    user = session.scalar(select(m.User).where(m.User.email == body.email))
    if not passwords.verify_password(user.password_hash if user else None, body.password):
        rate_limit.record(session, m.AuthEventKind.LOGIN_FAILED, email=body.email, ip=ip, now=now)
        return AuthFailure(ErrorCode.INVALID_CREDENTIALS, "Email hoặc mật khẩu không đúng")
    assert user is not None
    if user.status != UserStatus.ACTIVE:
        return AuthFailure(ACCOUNT_STATUS_ERRORS[user.status], _status_message(user.status))
    if passwords.needs_rehash(user.password_hash):
        user.password_hash = passwords.hash_password(body.password)
    issued = sessions.create(session, user.id, now=now, user_agent=user_agent, ip=ip)
    rate_limit.record(session, m.AuthEventKind.LOGIN_SUCCESS, email=user.email, ip=ip, now=now)
    return LoginSuccess(build_me(user, load_roles(session, user.id)), issued)


def _status_message(status: UserStatus) -> str:
    return {
        UserStatus.PENDING: "Tài khoản đang chờ admin duyệt",
        UserStatus.REJECTED: "Yêu cầu truy cập đã bị từ chối",
        UserStatus.DISABLED: "Tài khoản đã bị vô hiệu hóa",
    }[status]


def logout(
    session: Session, *, session_id: UUID, email: str, ip: str | None, now: datetime
) -> None:
    sessions.revoke(session, session_id, now=now)
    rate_limit.record(session, m.AuthEventKind.LOGOUT, email=email, ip=ip, now=now)


def change_password(
    session: Session, *, user_id: UUID, session_id: UUID, body: PasswordChange, now: datetime
) -> AuthFailure | None:
    user = session.get_one(m.User, user_id, with_for_update=True)
    if not passwords.verify_password(user.password_hash, body.current_password):
        return AuthFailure(ErrorCode.INVALID_REQUEST, "Mật khẩu hiện tại không đúng")
    violation = passwords.violates_policy(body.new_password, user.email)
    if violation is not None:
        return AuthFailure(ErrorCode.VALIDATION_ERROR, violation)
    user.password_hash = passwords.hash_password(body.new_password)
    sessions.revoke_all(session, user.id, now=now, keep=session_id)
    audit.record(
        session,
        actor=user,
        action="user.password_changed",
        entity_type="user",
        entity_id=user.id,
    )
    return None


def consume_password_reset(
    session: Session, body: PasswordResetConsume, *, now: datetime
) -> AuthFailure | None:
    token = session.scalar(
        select(m.PasswordResetToken)
        .where(m.PasswordResetToken.token_sha256 == sessions.token_sha256(body.token))
        .with_for_update()
    )
    if token is None or token.used_at is not None or token.expires_at <= now:
        return AuthFailure(
            ErrorCode.INVALID_REQUEST, "Link đặt lại mật khẩu không hợp lệ hoặc đã hết hạn"
        )
    user = session.get_one(m.User, token.user_id, with_for_update=True)
    violation = passwords.violates_policy(body.new_password, user.email)
    if violation is not None:
        return AuthFailure(ErrorCode.VALIDATION_ERROR, violation)
    token.used_at = now
    user.password_hash = passwords.hash_password(body.new_password)
    sessions.revoke_all(session, user.id, now=now)
    audit.record(
        session,
        actor=user,
        action="user.password_reset",
        entity_type="user",
        entity_id=user.id,
    )
    return None
