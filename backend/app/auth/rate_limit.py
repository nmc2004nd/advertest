"""Giới hạn đăng nhập sai (requirements.md Phase 4): quá 5 lần trong 15 phút cho cùng email
hoặc cùng IP → `429 rate_limited`, kể cả khi mật khẩu đúng.

Chỉ đếm `login_failed` (sai email hoặc mật khẩu). Lần bị chặn bằng 429 và lần đúng mật khẩu
nhưng tài khoản chưa `active` không ghi sự kiện (người dùng chốt, Phase 4 Group 1).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from backend.app.db import models as m

WINDOW = timedelta(minutes=15)
MAX_FAILURES = 5


def _failures(
    session: Session, column: InstrumentedAttribute[str | None], value: str, since: datetime
) -> int:
    return (
        session.scalar(
            select(func.count())
            .select_from(m.AuthEvent)
            .where(
                column == value,
                m.AuthEvent.kind == m.AuthEventKind.LOGIN_FAILED,
                m.AuthEvent.created_at > since,
            )
        )
        or 0
    )


def is_limited(session: Session, *, email: str, ip: str | None, now: datetime) -> bool:
    since = now - WINDOW
    if _failures(session, m.AuthEvent.email, email, since) >= MAX_FAILURES:
        return True
    return ip is not None and _failures(session, m.AuthEvent.ip, ip, since) >= MAX_FAILURES


def record(
    session: Session, kind: m.AuthEventKind, *, email: str, ip: str | None, now: datetime
) -> None:
    session.add(m.AuthEvent(email=email, ip=ip, kind=kind, created_at=now))
