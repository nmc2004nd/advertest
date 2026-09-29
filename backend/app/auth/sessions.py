"""Phiên đăng nhập phía server (requirements.md Phase 4, mục Phiên và bảo mật).

Cookie `advertest_session` chứa token ngẫu nhiên; DB chỉ lưu sha256 của token. Phiên hết hạn
tuyệt đối sau 12 giờ, không gia hạn. Cookie `csrf_token` (không httpOnly) dùng cho CSRF kiểu
double-submit.
"""

from __future__ import annotations

import hashlib
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from fastapi import Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from advertest_contracts.enums import UserStatus
from backend.app.api.security import SESSION_COOKIE
from backend.app.db import models as m

SESSION_TTL = timedelta(hours=12)
# Không ghi last_seen_at ở mọi request: đủ để theo dõi mà không thêm một lệnh UPDATE mỗi lần.
LAST_SEEN_RESOLUTION = timedelta(minutes=1)
CSRF_COOKIE = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"


def token_sha256(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)


def cookie_secure() -> bool:
    return os.environ.get("COOKIE_SECURE", "false").strip().lower() in {"1", "true", "yes"}


@dataclass(frozen=True)
class IssuedSession:
    id: UUID
    token: str
    csrf_token: str
    expires_at: datetime


def create(
    session: Session, user_id: UUID, *, now: datetime, user_agent: str | None, ip: str | None
) -> IssuedSession:
    token = new_token()
    row = m.UserSession(
        user_id=user_id,
        token_sha256=token_sha256(token),
        created_at=now,
        expires_at=now + SESSION_TTL,
        last_seen_at=now,
        user_agent=(user_agent or None) and user_agent[:512],
        ip=ip,
    )
    session.add(row)
    session.flush()
    return IssuedSession(row.id, token, new_token(), row.expires_at)


def lookup(session: Session, token: str, *, now: datetime) -> tuple[m.UserSession, m.User] | None:
    """Phiên còn hiệu lực của một user `active`, ngược lại None."""
    found = session.execute(
        select(m.UserSession, m.User)
        .join(m.User, m.User.id == m.UserSession.user_id)
        .where(
            m.UserSession.token_sha256 == token_sha256(token),
            m.UserSession.revoked_at.is_(None),
            m.UserSession.expires_at > now,
        )
    ).one_or_none()
    if found is None:
        return None
    row, user = found.tuple()
    if user.status != UserStatus.ACTIVE:
        return None
    if now - row.last_seen_at >= LAST_SEEN_RESOLUTION:
        row.last_seen_at = now
    return row, user


def revoke(session: Session, session_id: UUID, *, now: datetime) -> None:
    session.execute(
        update(m.UserSession)
        .where(m.UserSession.id == session_id, m.UserSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )


def revoke_all(session: Session, user_id: UUID, *, now: datetime, keep: UUID | None = None) -> None:
    """Thu hồi mọi phiên còn mở của user, trừ phiên `keep` (nếu có)."""
    query = update(m.UserSession).where(
        m.UserSession.user_id == user_id, m.UserSession.revoked_at.is_(None)
    )
    if keep is not None:
        query = query.where(m.UserSession.id != keep)
    session.execute(query.values(revoked_at=now))


def set_cookies(response: Response, issued: IssuedSession, *, now: datetime) -> None:
    max_age = int((issued.expires_at - now).total_seconds())
    secure = cookie_secure()
    response.set_cookie(
        SESSION_COOKIE,
        issued.token,
        max_age=max_age,
        path="/",
        secure=secure,
        httponly=True,
        samesite="lax",
    )
    response.set_cookie(
        CSRF_COOKIE,
        issued.csrf_token,
        max_age=max_age,
        path="/",
        secure=secure,
        httponly=False,
        samesite="lax",
    )


def clear_cookies(response: Response) -> None:
    secure = cookie_secure()
    response.delete_cookie(SESSION_COOKIE, path="/", secure=secure, httponly=True, samesite="lax")
    response.delete_cookie(CSRF_COOKIE, path="/", secure=secure, httponly=False, samesite="lax")
