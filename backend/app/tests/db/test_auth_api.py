"""Endpoint xác thực qua HTTP với Postgres thật (validation.md Phase 4: test_auth, test_csrf,
phần đổi mật khẩu của test_immediate_effect, phần dùng link đặt lại của test_admin, auth_events).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from advertest_contracts.enums import Role, UserStatus
from advertest_contracts.models import ErrorResponse, Me
from backend.app.api.deps import get_clock, get_sessionmaker
from backend.app.api.security import SESSION_COOKIE
from backend.app.auth import passwords, sessions
from backend.app.auth.sessions import CSRF_COOKIE, CSRF_HEADER
from backend.app.db import models as m
from backend.app.main import create_app

from .test_worker_services import FakeClock

pytestmark = pytest.mark.db
PASSWORD = "mat-khau-du-dai-1"
NEW_PASSWORD = "mat-khau-moi-dai-2"


@dataclass
class Env:
    engine: Engine
    clock: FakeClock
    ip: str
    monkeypatch: pytest.MonkeyPatch

    def client(self, ip: str | None = None) -> TestClient:
        """Client mới (cookie riêng); IP gốc gửi qua X-Forwarded-For từ proxy tin cậy."""
        app = create_app()
        factory = sessionmaker(self.engine)
        app.dependency_overrides[get_sessionmaker] = lambda: factory
        app.dependency_overrides[get_clock] = lambda: self.clock
        return TestClient(app, headers={"X-Forwarded-For": ip or self.ip})


@pytest.fixture
def env(app_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[Env]:
    # Client của TestClient có host "testclient": coi là proxy tin cậy để test chọn được IP.
    monkeypatch.setenv("TRUSTED_PROXIES", "testclient")
    yield Env(app_engine, FakeClock(), _random_ip(), monkeypatch)


def _random_ip() -> str:
    raw = uuid.uuid4().bytes
    return f"10.{raw[0]}.{raw[1]}.{raw[2] or 1}"


def _email() -> str:
    return f"u-{uuid.uuid4().hex[:10]}@x.test"


def _user(
    engine: Engine,
    *,
    status: UserStatus = UserStatus.ACTIVE,
    roles: tuple[Role, ...] = (Role.ENGINEER,),
    password: str = PASSWORD,
) -> tuple[uuid.UUID, str]:
    email = _email()
    with Session(engine) as session, session.begin():
        user = m.User(
            email=email,
            full_name="Người dùng",
            password_hash=passwords.hash_password(password),
            status=status,
        )
        session.add(user)
        session.flush()
        for role in roles:
            session.add(m.UserRole(user_id=user.id, role=role))
        return user.id, email


def _error(response: httpx.Response) -> tuple[int, str, str]:
    body = ErrorResponse.model_validate(response.json())
    return response.status_code, body.error.code, body.error.message


def _login(client: TestClient, email: str, password: str = PASSWORD) -> httpx.Response:
    response: httpx.Response = client.post(
        "/auth/login", json={"email": email, "password": password}
    )
    return response


def _csrf(client: TestClient) -> dict[str, str]:
    return {CSRF_HEADER: client.cookies.get(CSRF_COOKIE) or ""}


def _count(engine: Engine, query: Any) -> int:
    with Session(engine) as session:
        return int(session.scalar(query) or 0)


def _audit_count(engine: Engine, entity_id: uuid.UUID, action: str) -> int:
    return _count(
        engine,
        select(func.count())
        .select_from(m.AuditLog)
        .where(m.AuditLog.entity_id == entity_id, m.AuditLog.action == action),
    )


def _access_body(email: str, password: str = PASSWORD) -> dict[str, str]:
    return {
        "full_name": "Trần Thị Bích",
        "email": email,
        "organization": "VinAI",
        "requested_role": "engineer",
        "reason": "Kiểm thử model",
        "password": password,
    }


# ---------------------------------------------------------------- Yêu cầu truy cập


def test_request_access_creates_pending_user_with_argon2id(env: Env) -> None:
    email = _email()
    response = env.client().post("/auth/request-access", json=_access_body(email.upper()))
    assert response.status_code == 202
    assert response.content == b""
    with Session(env.engine) as session:
        user = session.scalars(select(m.User).where(m.User.email == email)).one()
        assert user.status == UserStatus.PENDING
        assert user.requested_role == Role.ENGINEER
        assert user.password_hash.startswith("$argon2id$")
        assert PASSWORD not in user.password_hash
        entry = session.scalars(select(m.AuditLog).where(m.AuditLog.entity_id == user.id)).one()
        assert (entry.action, entry.actor_id) == ("user.access_requested", user.id)
        assert entry.before is None
        assert entry.after == {"status": "pending", "roles": []}


def test_request_access_with_existing_email_looks_identical(env: Env) -> None:
    email = _email()
    client = env.client()
    first = client.post("/auth/request-access", json=_access_body(email))
    again = client.post("/auth/request-access", json=_access_body(email.upper(), "khac-hoan-toan"))
    assert (again.status_code, again.content) == (first.status_code, first.content)
    assert _count(env.engine, select(func.count()).where(m.User.email == email)) == 1
    with Session(env.engine) as session:
        user_id = session.scalars(select(m.User.id).where(m.User.email == email)).one()
    assert _audit_count(env.engine, user_id, "user.access_requested") == 1


# ---------------------------------------------------------------- Đăng nhập


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (UserStatus.PENDING, "account_pending"),
        (UserStatus.REJECTED, "account_rejected"),
        (UserStatus.DISABLED, "account_disabled"),
    ],
)
def test_inactive_account_with_right_password_gets_403_and_no_session(
    env: Env, status: UserStatus, code: str
) -> None:
    user_id, email = _user(env.engine, status=status)
    response = _login(env.client(), email)
    assert _error(response)[:2] == (403, code)
    assert "set-cookie" not in response.headers
    assert _count(env.engine, select(func.count()).where(m.UserSession.user_id == user_id)) == 0
    # Không phải sai mật khẩu: không ghi auth_events, không tính vào giới hạn.
    assert _count(env.engine, select(func.count()).where(m.AuthEvent.email == email)) == 0


def test_wrong_password_and_unknown_email_look_the_same(env: Env) -> None:
    _, email = _user(env.engine)
    wrong = _error(_login(env.client(), email, "sai-mat-khau-roi"))
    unknown = _error(_login(env.client(), _email()))
    assert wrong == unknown
    assert wrong[:2] == (401, "invalid_credentials")


def test_login_is_case_insensitive_on_email(env: Env) -> None:
    _, email = _user(env.engine)
    assert _login(env.client(), email.upper()).status_code == 200


def test_sixth_attempt_after_five_failures_is_rate_limited_even_with_right_password(
    env: Env,
) -> None:
    _, email = _user(env.engine)
    for i in range(5):
        # Mỗi lần từ một IP khác: chỉ giới hạn theo email được thử.
        assert _login(env.client(_random_ip()), email, f"sai-{i}-mat-khau").status_code == 401
    assert _error(_login(env.client(_random_ip()), email))[:2] == (429, "rate_limited")
    env.clock.advance(15 * 60 + 1)
    assert _login(env.client(_random_ip()), email).status_code == 200


def test_rate_limit_by_ip_does_not_block_other_ips(env: Env) -> None:
    _, email = _user(env.engine)
    for _ in range(5):
        assert _login(env.client(), _email(), "sai-mat-khau-x").status_code == 401
    assert _error(_login(env.client(), email))[:2] == (429, "rate_limited")
    assert _login(env.client(_random_ip()), email).status_code == 200


def test_forwarded_for_from_untrusted_peer_is_ignored(env: Env) -> None:
    env.monkeypatch.setenv("TRUSTED_PROXIES", "127.0.0.1")
    _, email = _user(env.engine)
    assert _login(env.client("203.0.113.9"), email).status_code == 200
    with Session(env.engine) as session:
        ips = set(session.scalars(select(m.AuthEvent.ip).where(m.AuthEvent.email == email)))
    assert ips == {"testclient"}


def test_successful_login_sets_cookie_flags_and_stores_only_sha256(env: Env) -> None:
    user_id, email = _user(env.engine, roles=(Role.ENGINEER, Role.REVIEWER))
    response = _login(env.client(), email)
    assert response.status_code == 200
    me = Me.model_validate(response.json())
    assert (me.id, set(me.roles)) == (user_id, {Role.ENGINEER, Role.REVIEWER})
    cookies = {c.split("=", 1)[0]: c.lower() for c in response.headers.get_list("set-cookie")}
    session_cookie, csrf_cookie = cookies[SESSION_COOKIE], cookies[CSRF_COOKIE]
    for cookie in (session_cookie, csrf_cookie):
        assert "samesite=lax" in cookie and "max-age=43200" in cookie and "path=/" in cookie
        assert "secure" not in cookie
    assert "httponly" in session_cookie
    assert "httponly" not in csrf_cookie
    token = response.cookies[SESSION_COOKIE]
    with Session(env.engine) as session:
        row = session.scalars(select(m.UserSession).where(m.UserSession.user_id == user_id)).one()
        assert row.token_sha256 == sessions.token_sha256(token)
        assert row.ip == env.ip
        kinds = list(session.scalars(select(m.AuthEvent.kind).where(m.AuthEvent.email == email)))
    assert kinds == [m.AuthEventKind.LOGIN_SUCCESS]


def test_cookie_secure_flag_follows_setting(env: Env) -> None:
    env.monkeypatch.setenv("COOKIE_SECURE", "true")
    _, email = _user(env.engine)
    response = _login(env.client(), email)
    assert all("secure" in c.lower() for c in response.headers.get_list("set-cookie"))


def test_me_and_session_expiry_after_12_hours(env: Env) -> None:
    _, email = _user(env.engine)
    client = env.client()
    _login(client, email)
    assert Me.model_validate(client.get("/auth/me").json()).email == email
    env.clock.advance(12 * 3600 - 1)
    assert client.get("/auth/me").status_code == 200
    env.clock.advance(1)
    assert _error(client.get("/auth/me"))[:2] == (401, "unauthenticated")


def test_logout_revokes_session_and_clears_cookies(env: Env) -> None:
    _, email = _user(env.engine)
    client = env.client()
    _login(client, email)
    old_token = client.cookies[SESSION_COOKIE]
    response = client.post("/auth/logout", headers=_csrf(client))
    assert response.status_code == 204
    cleared = [c.lower() for c in response.headers.get_list("set-cookie")]
    assert {c.split("=", 1)[0] for c in cleared} == {SESSION_COOKIE, CSRF_COOKIE}
    assert all("max-age=0" in c for c in cleared)
    reuse = env.client()
    reuse.cookies.set(SESSION_COOKIE, old_token)
    assert _error(reuse.get("/auth/me"))[:2] == (401, "unauthenticated")
    with Session(env.engine) as session:
        kinds = list(
            session.scalars(
                select(m.AuthEvent.kind)
                .where(m.AuthEvent.email == email)
                .order_by(m.AuthEvent.created_at)
            )
        )
    assert kinds == [m.AuthEventKind.LOGIN_SUCCESS, m.AuthEventKind.LOGOUT]


def test_disabled_user_session_is_rejected_on_next_request(env: Env) -> None:
    user_id, email = _user(env.engine)
    client = env.client()
    _login(client, email)
    with Session(env.engine) as session, session.begin():
        session.get_one(m.User, user_id).status = UserStatus.DISABLED
    assert _error(client.get("/auth/me"))[:2] == (401, "unauthenticated")


# ---------------------------------------------------------------- CSRF với phiên thật


def test_csrf_required_with_real_session(env: Env) -> None:
    _, email = _user(env.engine)
    client = env.client()
    _login(client, email)
    assert _error(client.post("/auth/logout"))[:2] == (403, "csrf_failed")
    assert _error(client.post("/auth/logout", headers={CSRF_HEADER: "sai"}))[:2] == (
        403,
        "csrf_failed",
    )
    assert client.get("/auth/me").status_code == 200


# ---------------------------------------------------------------- Đổi mật khẩu


def test_change_password_revokes_other_sessions_and_keeps_current(env: Env) -> None:
    user_id, email = _user(env.engine)
    current, other = env.client(), env.client()
    _login(current, email)
    _login(other, email)
    response = current.post(
        "/auth/password",
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        headers=_csrf(current),
    )
    assert response.status_code == 204
    assert current.get("/auth/me").status_code == 200
    assert other.get("/auth/me").status_code == 401
    assert _login(env.client(), email, NEW_PASSWORD).status_code == 200
    assert _audit_count(env.engine, user_id, "user.password_changed") == 1


def test_change_password_with_wrong_current_is_422_and_keeps_session(env: Env) -> None:
    user_id, email = _user(env.engine)
    client = env.client()
    _login(client, email)
    response = client.post(
        "/auth/password",
        json={"current_password": "sai-mat-khau-hien-tai", "new_password": NEW_PASSWORD},
        headers=_csrf(client),
    )
    assert _error(response)[:2] == (422, "invalid_request")
    assert client.get("/auth/me").status_code == 200
    assert _audit_count(env.engine, user_id, "user.password_changed") == 0


@pytest.mark.parametrize("new_password", ["ngan-9-kt", "EMAIL"])
def test_change_password_enforces_policy(env: Env, new_password: str) -> None:
    _, email = _user(env.engine)
    client = env.client()
    _login(client, email)
    value = email.upper() if new_password == "EMAIL" else new_password
    response = client.post(
        "/auth/password",
        json={"current_password": PASSWORD, "new_password": value},
        headers=_csrf(client),
    )
    assert _error(response)[:2] == (422, "validation_error")


# ---------------------------------------------------------------- Link đặt lại mật khẩu


def _reset_token(env: Env, user_id: uuid.UUID, *, hours: float = 24) -> str:
    """Token như Group 3 sẽ tạo (link do admin tạo, hết hạn sau 24 giờ)."""
    token = sessions.new_token()
    with Session(env.engine) as session, session.begin():
        session.add(
            m.PasswordResetToken(
                user_id=user_id,
                token_sha256=sessions.token_sha256(token),
                created_by=user_id,
                expires_at=env.clock() + timedelta(hours=hours),
            )
        )
    return token


def test_reset_link_is_single_use_and_revokes_every_session(env: Env) -> None:
    user_id, email = _user(env.engine)
    logged_in = env.client()
    _login(logged_in, email)
    token = _reset_token(env, user_id)
    body = {"token": token, "new_password": NEW_PASSWORD}
    assert env.client().post("/auth/password-reset", json=body).status_code == 204
    assert logged_in.get("/auth/me").status_code == 401
    assert _login(env.client(), email, NEW_PASSWORD).status_code == 200
    again = env.client().post("/auth/password-reset", json=body | {"new_password": PASSWORD})
    assert _error(again)[:2] == (422, "invalid_request")
    with Session(env.engine) as session:
        entry = session.scalars(
            select(m.AuditLog).where(
                m.AuditLog.entity_id == user_id, m.AuditLog.action == "user.password_reset"
            )
        ).one()
        assert entry.actor_id == user_id
        assert token not in str(entry.before) + str(entry.after)


def test_reset_link_expires_after_24_hours(env: Env) -> None:
    user_id, _ = _user(env.engine)
    token = _reset_token(env, user_id)
    env.clock.advance(24 * 3600)
    response = env.client().post(
        "/auth/password-reset", json={"token": token, "new_password": NEW_PASSWORD}
    )
    assert _error(response)[:2] == (422, "invalid_request")


def test_reset_enforces_password_policy(env: Env) -> None:
    user_id, email = _user(env.engine)
    token = _reset_token(env, user_id)
    response = env.client().post(
        "/auth/password-reset", json={"token": token, "new_password": email}
    )
    assert _error(response)[:2] == (422, "validation_error")


# ---------------------------------------------------------------- auth_events và audit_log


def test_login_events_are_not_written_to_audit_log(env: Env) -> None:
    user_id, email = _user(env.engine)
    client = env.client()
    _login(client, email, "sai-mat-khau-roi")
    _login(client, email)
    client.post("/auth/logout", headers=_csrf(client))
    assert _count(env.engine, select(func.count()).where(m.AuthEvent.email == email)) == 3
    assert _count(env.engine, select(func.count()).where(m.AuditLog.entity_id == user_id)) == 0
