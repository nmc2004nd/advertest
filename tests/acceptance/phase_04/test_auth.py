"""validation.md Phase 4, Yêu cầu truy cập và đăng nhập (`test_auth.py`)."""

from __future__ import annotations

import hashlib

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.db import models as m

from .conftest import (
    CSRF_COOKIE,
    PASSWORD,
    SESSION_COOKIE,
    Api,
    access_body,
    error,
    login,
    new_email,
    ok,
    post,
    random_ip,
)

pytestmark = pytest.mark.db


def test_request_access_creates_pending_user_with_argon2id(api: Api) -> None:
    email = new_email()
    response = api.client().post("/auth/request-access", json=access_body(email))
    assert response.status_code == 202
    with Session(api.engine) as session:
        user = session.scalars(select(m.User).where(m.User.email == email)).one()
    assert user.status == "pending"
    assert user.password_hash.startswith("$argon2id$")
    assert PASSWORD not in user.password_hash


def test_existing_email_gets_same_response_and_no_new_user(api: Api) -> None:
    email = new_email()
    first = api.client().post("/auth/request-access", json=access_body(email))
    again = api.client().post("/auth/request-access", json=access_body(email, "khac-han-hoan-toan"))
    assert (again.status_code, again.content) == (first.status_code, first.content)
    with Session(api.engine) as session:
        assert session.scalar(select(func.count()).where(m.User.email == email)) == 1


def test_email_is_case_insensitive(api: Api) -> None:
    email = new_email()
    api.request_access(email.upper())
    api.request_access(email)
    with Session(api.engine) as session:
        assert session.scalar(select(func.count()).where(m.User.email == email)) == 1
    _, active = api.create_user("engineer")
    assert login(api.client(), active.upper()).status_code == 200


@pytest.mark.parametrize("password", ["123456789", "EMAIL"])
def test_request_access_password_policy(api: Api, password: str) -> None:
    email = new_email()
    body = access_body(email, email.upper() if password == "EMAIL" else password)
    assert error(api.client().post("/auth/request-access", json=body)) == (422, "validation_error")


def test_password_policy_for_change_and_reset(api: Api) -> None:
    user_id, email, client = api.logged_in("engineer")
    for new in ("ngan-9-kt", email.upper()):
        response = post(
            client, "/auth/password", {"current_password": PASSWORD, "new_password": new}
        )
        assert error(response) == (422, "validation_error")
    link = post(api.admin(), f"/admin/users/{user_id}/reset-link").json()["url"]
    token = link.rsplit("/", 1)[1]
    response = api.client().post(
        "/auth/password-reset", json={"token": token, "new_password": email}
    )
    assert error(response) == (422, "validation_error")


@pytest.mark.parametrize(
    ("status", "code"),
    [
        ("pending", "account_pending"),
        ("rejected", "account_rejected"),
        ("disabled", "account_disabled"),
    ],
)
def test_inactive_account_gets_403_and_no_session_cookie(api: Api, status: str, code: str) -> None:
    _, email = api.create_user("engineer", status=status)
    response = login(api.client(), email)
    assert error(response) == (403, code)
    assert "set-cookie" not in response.headers


def test_wrong_password_and_unknown_email_look_the_same(api: Api) -> None:
    _, email = api.create_user("engineer")
    wrong = login(api.client(), email, "sai-mat-khau-roi")
    unknown = login(api.client(), new_email(), PASSWORD)
    assert error(wrong) == error(unknown) == (401, "invalid_credentials")
    assert wrong.json()["error"]["message"] == unknown.json()["error"]["message"]


def test_sixth_attempt_is_rate_limited_even_with_right_password(api: Api) -> None:
    _, email = api.create_user("engineer")
    for i in range(5):
        assert login(api.client(), email, f"sai-{i}-mat-khau").status_code == 401
    assert error(login(api.client(), email)) == (429, "rate_limited")


def test_rate_limit_uses_origin_ip_from_trusted_proxy_only(
    api: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, email = api.create_user("engineer")
    blocked_ip = random_ip()
    for _ in range(5):
        assert login(api.client(blocked_ip), new_email(), "sai-mat-khau-x").status_code == 401
    assert error(login(api.client(blocked_ip), email)) == (429, "rate_limited")
    # IP gốc khác không bị khóa lây.
    assert login(api.client(random_ip()), email).status_code == 200
    # X-Forwarded-For từ nguồn không tin cậy bị bỏ qua: IP ghi nhận là địa chỉ kết nối.
    monkeypatch.setenv("TRUSTED_PROXIES", "127.0.0.1")
    _, other = api.create_user("engineer")
    assert login(api.client("203.0.113.7"), other).status_code == 200
    with Session(api.engine) as session:
        ips = set(session.scalars(select(m.AuthEvent.ip).where(m.AuthEvent.email == other)))
    assert "203.0.113.7" not in ips


def test_login_cookies_and_sha256_only(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    user_id, email = api.create_user("engineer")
    client = api.client()
    response = ok(login(client, email))
    cookies = {c.split("=", 1)[0]: c.lower() for c in response.headers.get_list("set-cookie")}
    assert "httponly" in cookies[SESSION_COOKIE] and "samesite=lax" in cookies[SESSION_COOKIE]
    assert "secure" not in cookies[SESSION_COOKIE]
    assert "httponly" not in cookies[CSRF_COOKIE]
    token = client.cookies[SESSION_COOKIE]
    with Session(api.engine) as session:
        stored = session.scalars(
            select(m.UserSession.token_sha256).where(m.UserSession.user_id == user_id)
        ).all()
    assert hashlib.sha256(token.encode()).hexdigest() in stored
    assert token not in stored
    cleared = post(client, "/auth/logout").headers.get_list("set-cookie")
    assert {c.split("=", 1)[0] for c in cleared} == {SESSION_COOKIE, CSRF_COOKIE}
    assert all("max-age=0" in c.lower() for c in cleared)

    monkeypatch.setenv("COOKIE_SECURE", "true")
    secure = login(api.client(), email).headers.get_list("set-cookie")
    assert all("secure" in c.lower() for c in secure)


def test_session_expires_after_12_hours(api: Api) -> None:
    _, _, client = api.logged_in("engineer")
    api.clock.advance(hours=11, minutes=59)
    assert client.get("/auth/me").status_code == 200
    api.clock.advance(minutes=1)
    assert error(client.get("/auth/me")) == (401, "unauthenticated")


def test_reusing_cookie_after_logout_is_401(api: Api) -> None:
    _, _, client = api.logged_in("engineer")
    token = client.cookies[SESSION_COOKIE]
    ok(post(client, "/auth/logout"))
    reuse = api.client()
    reuse.cookies.set(SESSION_COOKIE, token)
    assert error(reuse.get("/auth/me")) == (401, "unauthenticated")
