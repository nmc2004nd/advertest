"""Quản trị người dùng và audit log qua HTTP với Postgres thật (validation.md Phase 4:
test_admin, test_audit_phase04, phần vô hiệu hóa và đổi role của test_immediate_effect)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from advertest_contracts.enums import Role, UserStatus
from advertest_contracts.models import (
    AuditLogPage,
    ErrorResponse,
    PasswordResetLink,
    UserAdminPage,
    UserAdminView,
)
from backend.app.admin import users as admin_users
from backend.app.auth.sessions import CSRF_COOKIE, CSRF_HEADER
from backend.app.db import models as m
from backend.app.services.errors import Conflict

from .test_auth_api import (
    NEW_PASSWORD,
    PASSWORD,
    Env,
    _access_body,
    _email,
    _login,
    _user,
    env,  # fixture dùng chung
)

pytestmark = pytest.mark.db
__all__ = ["env"]


def _csrf(client: TestClient) -> dict[str, str]:
    return {CSRF_HEADER: client.cookies.get(CSRF_COOKIE) or ""}


def _error(response: httpx.Response) -> tuple[int, str]:
    body = ErrorResponse.model_validate(response.json())
    return response.status_code, body.error.code


def _admin(env: Env) -> tuple[uuid.UUID, TestClient]:
    admin_id, email = _user(env.engine, roles=(Role.ADMIN,))
    client = env.client()
    assert _login(client, email).status_code == 200
    return admin_id, client


def _post(client: TestClient, path: str, body: Any = None) -> httpx.Response:
    response: httpx.Response = client.post(path, json=body, headers=_csrf(client))
    return response


def _pending(env: Env) -> tuple[uuid.UUID, str]:
    email = _email()
    assert env.client().post("/auth/request-access", json=_access_body(email)).status_code == 202
    with Session(env.engine) as session:
        return session.scalars(select(m.User.id).where(m.User.email == email)).one(), email


def _audit(env: Env, user_id: uuid.UUID, action: str) -> list[m.AuditLog]:
    with Session(env.engine) as session:
        return list(
            session.scalars(
                select(m.AuditLog).where(
                    m.AuditLog.entity_id == user_id, m.AuditLog.action == action
                )
            )
        )


# ---------------------------------------------------------------- Duyệt, từ chối


def test_approve_requires_a_role(env: Env) -> None:
    _, admin = _admin(env)
    user_id, _ = _pending(env)
    response = _post(admin, f"/admin/users/{user_id}/approve", {"roles": []})
    assert _error(response) == (422, "validation_error")


def test_approve_activates_with_roles_and_user_can_log_in(env: Env) -> None:
    admin_id, admin = _admin(env)
    user_id, email = _pending(env)
    response = _post(admin, f"/admin/users/{user_id}/approve", {"roles": ["engineer"]})
    assert response.status_code == 200
    view = UserAdminView.model_validate(response.json())
    assert (view.status, view.roles, view.approved_by) == (
        UserStatus.ACTIVE,
        [Role.ENGINEER],
        admin_id,
    )
    assert _login(env.client(), email).status_code == 200
    [entry] = _audit(env, user_id, "user.approved")
    assert entry.actor_id == admin_id
    assert (entry.before, entry.after) == (
        {"status": "pending", "roles": []},
        {"status": "active", "roles": ["engineer"]},
    )


def test_reject_requires_reason_and_stores_it(env: Env) -> None:
    admin_id, admin = _admin(env)
    user_id, email = _pending(env)
    assert _error(_post(admin, f"/admin/users/{user_id}/reject", {"reason": ""})) == (
        422,
        "validation_error",
    )
    response = _post(admin, f"/admin/users/{user_id}/reject", {"reason": "Không thuộc nhóm"})
    view = UserAdminView.model_validate(response.json())
    assert (view.status, view.reject_reason) == (UserStatus.REJECTED, "Không thuộc nhóm")
    assert _error(_login(env.client(), email)) == (403, "account_rejected")
    [entry] = _audit(env, user_id, "user.rejected")
    assert (entry.actor_id, entry.after) == (admin_id, {"status": "rejected", "roles": []})


# ---------------------------------------------------------------- Vô hiệu hóa, kích hoạt, role


def test_admin_cannot_disable_themself(env: Env) -> None:
    admin_id, admin = _admin(env)
    assert _error(_post(admin, f"/admin/users/{admin_id}/disable")) == (409, "conflict")


def test_disable_revokes_sessions_immediately_and_enable_restores(env: Env) -> None:
    _, admin = _admin(env)
    user_id, email = _user(env.engine)
    victim, other_device = env.client(), env.client()
    _login(victim, email)
    _login(other_device, email)
    response = _post(admin, f"/admin/users/{user_id}/disable")
    assert UserAdminView.model_validate(response.json()).status == UserStatus.DISABLED
    assert _error(victim.get("/auth/me")) == (401, "unauthenticated")
    assert _error(other_device.get("/auth/me")) == (401, "unauthenticated")
    with Session(env.engine) as session:
        open_sessions = session.scalars(
            select(m.UserSession).where(
                m.UserSession.user_id == user_id, m.UserSession.revoked_at.is_(None)
            )
        ).all()
    assert open_sessions == []
    assert _error(_login(env.client(), email)) == (403, "account_disabled")

    response = _post(admin, f"/admin/users/{user_id}/enable")
    assert UserAdminView.model_validate(response.json()).status == UserStatus.ACTIVE
    assert _login(env.client(), email).status_code == 200
    assert len(_audit(env, user_id, "user.disabled")) == 1
    assert len(_audit(env, user_id, "user.enabled")) == 1


def test_role_change_takes_effect_on_next_request(env: Env) -> None:
    _, admin = _admin(env)
    user_id, email = _user(env.engine, roles=(Role.ENGINEER,))
    client = env.client()
    _login(client, email)
    assert _post(client, "/experiments", {}).status_code != 403
    response = admin.put(
        f"/admin/users/{user_id}/roles", json={"roles": ["reviewer"]}, headers=_csrf(admin)
    )
    assert UserAdminView.model_validate(response.json()).roles == [Role.REVIEWER]
    assert _error(_post(client, "/experiments", {})) == (403, "forbidden")
    [entry] = _audit(env, user_id, "user.roles_changed")
    assert entry.before is not None and entry.after is not None
    assert (entry.before["roles"], entry.after["roles"]) == (["engineer"], ["reviewer"])


def test_empty_role_list_is_rejected(env: Env) -> None:
    _, admin = _admin(env)
    user_id, _ = _user(env.engine)
    response = admin.put(f"/admin/users/{user_id}/roles", json={"roles": []}, headers=_csrf(admin))
    assert _error(response) == (422, "validation_error")


def test_invalid_transitions_are_conflicts(env: Env) -> None:
    _, admin = _admin(env)
    active_id, _ = _user(env.engine)
    disabled_id, _ = _user(env.engine, status=UserStatus.DISABLED)
    pending_id, _ = _pending(env)
    assert _error(_post(admin, f"/admin/users/{active_id}/approve", {"roles": ["engineer"]})) == (
        409,
        "conflict",
    )
    assert _error(_post(admin, f"/admin/users/{active_id}/reject", {"reason": "x"})) == (
        409,
        "conflict",
    )
    assert _error(_post(admin, f"/admin/users/{active_id}/enable")) == (409, "conflict")
    assert _error(_post(admin, f"/admin/users/{disabled_id}/disable")) == (409, "conflict")
    # Đổi role và tạo link đặt lại chỉ cho user active/disabled (người dùng chốt, Group 3).
    roles = admin.put(
        f"/admin/users/{pending_id}/roles", json={"roles": ["engineer"]}, headers=_csrf(admin)
    )
    assert _error(roles) == (409, "conflict")
    assert _error(_post(admin, f"/admin/users/{pending_id}/reset-link")) == (409, "conflict")
    assert _error(_post(admin, f"/admin/users/{uuid.uuid4()}/enable")) == (404, "not_found")


def test_last_active_admin_cannot_lose_admin_or_be_disabled(env: Env) -> None:
    """Trong một transaction rồi rollback: tạm vô hiệu mọi admin khác của DB test dùng chung."""
    with Session(env.engine) as session, session.begin():
        actor = m.User(
            email=_email(), full_name="Actor", password_hash="x", status=UserStatus.ACTIVE
        )
        last = m.User(email=_email(), full_name="Last", password_hash="x", status=UserStatus.ACTIVE)
        session.add_all([actor, last])
        session.flush()
        session.add(m.UserRole(user_id=last.id, role=Role.ADMIN))
        session.flush()
        session.execute(
            update(m.User)
            .where(m.User.id != last.id, m.User.status == UserStatus.ACTIVE)
            .values(status=UserStatus.DISABLED)
        )
        with pytest.raises(Conflict, match="admin active cuối cùng"):
            admin_users.update_roles(session, actor, last.id, [Role.ENGINEER])
        with pytest.raises(Conflict, match="admin active cuối cùng"):
            admin_users.disable(session, actor, last.id, now=datetime.now(UTC))
        # Có thêm một admin active khác thì được.
        other = session.get_one(m.User, actor.id)
        other.status = UserStatus.ACTIVE
        session.add(m.UserRole(user_id=actor.id, role=Role.ADMIN))
        session.flush()
        admin_users.update_roles(session, actor, last.id, [Role.ENGINEER])
        session.rollback()


# ---------------------------------------------------------------- Link đặt lại mật khẩu


def test_reset_link_url_expiry_single_use_and_replacement(env: Env) -> None:
    env.monkeypatch.setenv("APP_BASE_URL", "https://advertest.example/")
    _, admin = _admin(env)
    user_id, email = _user(env.engine)
    logged_in = env.client()
    _login(logged_in, email)
    first = PasswordResetLink.model_validate(
        _post(admin, f"/admin/users/{user_id}/reset-link").json()
    )
    second = PasswordResetLink.model_validate(
        _post(admin, f"/admin/users/{user_id}/reset-link").json()
    )
    assert second.url.startswith("https://advertest.example/reset-password/")
    assert second.expires_at == env.clock() + timedelta(hours=24)
    first_token = first.url.rsplit("/", 1)[1]
    second_token = second.url.rsplit("/", 1)[1]
    # Link mới vô hiệu link cũ.
    old = env.client().post(
        "/auth/password-reset", json={"token": first_token, "new_password": NEW_PASSWORD}
    )
    assert _error(old) == (422, "invalid_request")
    body = {"token": second_token, "new_password": NEW_PASSWORD}
    assert env.client().post("/auth/password-reset", json=body).status_code == 204
    assert _error(env.client().post("/auth/password-reset", json=body)) == (
        422,
        "invalid_request",
    )
    assert logged_in.get("/auth/me").status_code == 401
    assert _login(env.client(), email, NEW_PASSWORD).status_code == 200
    entries = _audit(env, user_id, "user.reset_link_created")
    assert len(entries) == 2
    stored = json.dumps([[e.before, e.after] for e in entries])
    assert first_token not in stored and second_token not in stored


def test_reset_link_expires_after_24_hours(env: Env) -> None:
    _, admin = _admin(env)
    user_id, _ = _user(env.engine)
    link = PasswordResetLink.model_validate(
        _post(admin, f"/admin/users/{user_id}/reset-link").json()
    )
    env.clock.advance(24 * 3600)
    response = env.client().post(
        "/auth/password-reset",
        json={"token": link.url.rsplit("/", 1)[1], "new_password": NEW_PASSWORD},
    )
    assert _error(response) == (422, "invalid_request")


# ---------------------------------------------------------------- Quyền


@pytest.mark.parametrize("role", [Role.ENGINEER, Role.REVIEWER])
def test_non_admin_is_forbidden(env: Env, role: Role) -> None:
    target, _ = _user(env.engine)
    _, email = _user(env.engine, roles=(role,))
    client = env.client()
    _login(client, email)
    assert _error(client.get("/admin/users")) == (403, "forbidden")
    assert _error(_post(client, f"/admin/users/{target}/disable")) == (403, "forbidden")
    assert _error(client.get("/audit-log")) == (403, "forbidden")


# ---------------------------------------------------------------- Danh sách và phân trang


def _all_pages(client: TestClient, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    cursor: str | None = None
    for _ in range(1000):
        response = client.get(path, params=params | ({"cursor": cursor} if cursor else {}))
        assert response.status_code == 200, response.text
        page = response.json()
        items.extend(page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            return items
    raise AssertionError("Phân trang không kết thúc")


def test_user_list_filters_by_status_and_pages_without_gaps(env: Env) -> None:
    _, admin = _admin(env)
    created = {_pending(env)[0] for _ in range(5)}
    items = _all_pages(admin, "/admin/users", {"status": "pending", "limit": 2})
    UserAdminPage.model_validate({"items": items, "next_cursor": None})
    ids = [uuid.UUID(item["id"]) for item in items]
    assert len(ids) == len(set(ids))
    assert created <= set(ids)
    assert {item["status"] for item in items} == {"pending"}


def test_invalid_cursor_is_rejected(env: Env) -> None:
    _, admin = _admin(env)
    assert _error(admin.get("/admin/users", params={"cursor": "khong-hop-le"})) == (
        422,
        "invalid_request",
    )


# ---------------------------------------------------------------- Audit log


def test_audit_log_filters_pages_and_shows_actor(env: Env) -> None:
    admin_id, admin = _admin(env)
    user_ids = []
    for _ in range(3):
        user_id, _ = _pending(env)
        _post(admin, f"/admin/users/{user_id}/approve", {"roles": ["engineer"]})
        user_ids.append(user_id)
    items = _all_pages(admin, "/audit-log", {"actor_id": str(admin_id), "limit": 2})
    page = AuditLogPage.model_validate({"items": items, "next_cursor": None})
    assert [e.entity_id for e in page.items] == list(reversed(user_ids))
    assert all(e.action == "user.approved" for e in page.items)
    assert all(e.actor is not None and e.actor.id == admin_id for e in page.items)

    by_action = _all_pages(
        admin, "/audit-log", {"action": "user.access_requested", "entity_id": str(user_ids[0])}
    )
    [requested] = AuditLogPage.model_validate({"items": by_action, "next_cursor": None}).items
    assert requested.actor is not None and requested.actor.id == user_ids[0]

    newest = page.items[0].created_at
    since = _all_pages(
        admin,
        "/audit-log",
        {"actor_id": str(admin_id), "since": newest.isoformat()},
    )
    assert len(since) >= 1
    until = _all_pages(
        admin,
        "/audit-log",
        {"actor_id": str(admin_id), "until": (newest - timedelta(hours=1)).isoformat()},
    )
    assert until == []
    naive = admin.get("/audit-log", params={"since": "2026-09-29T00:00:00"})
    assert _error(naive) == (422, "invalid_request")


def test_no_audit_row_contains_passwords_hashes_or_tokens(env: Env) -> None:
    _, admin = _admin(env)
    user_id, email = _pending(env)
    _post(admin, f"/admin/users/{user_id}/approve", {"roles": ["engineer"]})
    client = env.client()
    _login(client, email)
    _post(client, "/auth/password", {"current_password": PASSWORD, "new_password": NEW_PASSWORD})
    link = _post(admin, f"/admin/users/{user_id}/reset-link").json()["url"]
    with Session(env.engine) as session:
        rows = session.execute(select(m.AuditLog.before, m.AuditLog.after)).all()
        hashes = session.scalars(select(m.User.password_hash)).all()
    dumped = json.dumps([list(r) for r in rows])
    for secret in (PASSWORD, NEW_PASSWORD, link.rsplit("/", 1)[1], "$argon2"):
        assert secret not in dumped
    assert not any(h in dumped for h in hashes)
