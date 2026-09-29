"""Phiên phía server (validation.md Phase 4: chỉ lưu sha256, hết hạn 12 giờ, thu hồi)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from advertest_contracts.enums import UserStatus
from backend.app.auth import sessions
from backend.app.db import models as m

from .conftest import make_user

pytestmark = pytest.mark.db
NOW = datetime(2026, 9, 29, 8, 0, tzinfo=UTC)


def test_only_sha256_of_token_is_stored(db: Session) -> None:
    user = make_user(db)
    issued = sessions.create(db, user.id, now=NOW, user_agent="ua", ip="10.0.0.1")
    row = db.get_one(m.UserSession, issued.id)
    assert row.token_sha256 == sessions.token_sha256(issued.token)
    assert issued.token not in {row.token_sha256, row.user_agent, row.ip}
    assert row.expires_at == NOW + timedelta(hours=12)


def test_lookup_respects_expiry_revocation_and_status(db: Session) -> None:
    user = make_user(db)
    issued = sessions.create(db, user.id, now=NOW, user_agent=None, ip=None)
    assert sessions.lookup(db, issued.token, now=NOW + timedelta(hours=11, minutes=59))
    assert sessions.lookup(db, issued.token, now=NOW + timedelta(hours=12)) is None
    assert sessions.lookup(db, "khong-ton-tai", now=NOW) is None

    user.status = UserStatus.DISABLED
    db.flush()
    assert sessions.lookup(db, issued.token, now=NOW) is None
    user.status = UserStatus.ACTIVE
    sessions.revoke(db, issued.id, now=NOW)
    assert sessions.lookup(db, issued.token, now=NOW) is None


def test_revoke_all_keeps_the_current_session(db: Session) -> None:
    user = make_user(db)
    keep = sessions.create(db, user.id, now=NOW, user_agent=None, ip=None)
    other = sessions.create(db, user.id, now=NOW, user_agent=None, ip=None)
    sessions.revoke_all(db, user.id, now=NOW, keep=keep.id)
    assert sessions.lookup(db, keep.token, now=NOW)
    assert sessions.lookup(db, other.token, now=NOW) is None
    sessions.revoke_all(db, user.id, now=NOW)
    open_rows = db.scalars(
        select(m.UserSession).where(
            m.UserSession.user_id == user.id, m.UserSession.revoked_at.is_(None)
        )
    ).all()
    assert open_rows == []
