"""validation.md Phase 4, Audit (`test_audit_phase04.py`)."""

from __future__ import annotations

import json
import uuid
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.db import models as m

from .conftest import (
    ADMIN_EMAIL,
    NEW_PASSWORD,
    PASSWORD,
    Api,
    error,
    login,
    ok,
    post,
    put,
)

pytestmark = pytest.mark.db


def _entries(api: Api, user_id: uuid.UUID) -> list[m.AuditLog]:
    with Session(api.engine) as session:
        return list(
            session.scalars(
                select(m.AuditLog)
                .where(m.AuditLog.entity_id == user_id)
                .order_by(m.AuditLog.created_at, m.AuditLog.id)
            )
        )


def test_every_account_action_writes_exactly_one_correct_row(api: Api) -> None:
    admin_id = api.user_id(ADMIN_EMAIL)
    admin = api.admin()
    rejected_id, _ = api.create_user("engineer", status="rejected")
    user_id, email = api.create_user("engineer", status="pending")
    ok(post(admin, f"/admin/users/{user_id}/approve", {"roles": ["engineer"]}))
    ok(put(admin, f"/admin/users/{user_id}/roles", {"roles": ["reviewer"]}))
    ok(post(admin, f"/admin/users/{user_id}/disable"))
    ok(post(admin, f"/admin/users/{user_id}/enable"))
    link = ok(post(admin, f"/admin/users/{user_id}/reset-link")).json()["url"]
    ok(
        api.client().post(
            "/auth/password-reset",
            json={"token": link.rsplit("/", 1)[1], "new_password": NEW_PASSWORD},
        )
    )
    client = api.client()
    ok(login(client, email, NEW_PASSWORD))
    ok(post(client, "/auth/password", {"current_password": NEW_PASSWORD, "new_password": PASSWORD}))

    rows = {e.action: e for e in _entries(api, user_id)}
    assert len(rows) == len(_entries(api, user_id)) == 8
    expected: dict[str, tuple[uuid.UUID, Any, Any]] = {
        "user.access_requested": (user_id, None, {"status": "pending", "roles": []}),
        "user.approved": (
            admin_id,
            {"status": "pending", "roles": []},
            {"status": "active", "roles": ["engineer"]},
        ),
        "user.roles_changed": (
            admin_id,
            {"status": "active", "roles": ["engineer"]},
            {"status": "active", "roles": ["reviewer"]},
        ),
        "user.disabled": (
            admin_id,
            {"status": "active", "roles": ["reviewer"]},
            {"status": "disabled", "roles": ["reviewer"]},
        ),
        "user.enabled": (
            admin_id,
            {"status": "disabled", "roles": ["reviewer"]},
            {"status": "active", "roles": ["reviewer"]},
        ),
        "user.reset_link_created": (
            admin_id,
            {"status": "active", "roles": ["reviewer"]},
            {"status": "active", "roles": ["reviewer"]},
        ),
        "user.password_reset": (user_id, None, None),
        "user.password_changed": (user_id, None, None),
    }
    for action, (actor, before, after) in expected.items():
        row = rows[action]
        assert (row.actor_id, row.entity_type, row.before, row.after) == (
            actor,
            "user",
            before,
            after,
        ), action
    [rejected] = [e for e in _entries(api, rejected_id) if e.action == "user.rejected"]
    assert (rejected.actor_id, rejected.after) == (admin_id, {"status": "rejected", "roles": []})


def test_audit_log_api_returns_actor_object_or_null(api: Api) -> None:
    user_id, _ = api.create_user("engineer")
    admin = api.admin()
    items = ok(admin.get("/audit-log", params={"entity_id": str(user_id)})).json()["items"]
    approved = next(i for i in items if i["action"] == "user.approved")
    assert set(approved["actor"]) == {"id", "full_name", "email"}
    assert approved["actor"]["email"] == ADMIN_EMAIL
    with Session(api.engine) as session, session.begin():
        session.add(m.AuditLog(actor_id=None, action="system.test", entity_type="system"))
    system = ok(admin.get("/audit-log", params={"action": "system.test"})).json()["items"]
    assert system[0]["actor"] is None


def test_no_audit_row_contains_passwords_hashes_or_tokens(api: Api) -> None:
    user_id, email, client = api.logged_in("engineer")
    ok(post(client, "/auth/password", {"current_password": PASSWORD, "new_password": NEW_PASSWORD}))
    token = (
        ok(post(api.admin(), f"/admin/users/{user_id}/reset-link")).json()["url"].rsplit("/", 1)[1]
    )
    with Session(api.engine) as session:
        dumped = json.dumps([[r.before, r.after] for r in session.scalars(select(m.AuditLog))])
        hashes = set(session.scalars(select(m.User.password_hash)))
    for secret in (PASSWORD, NEW_PASSWORD, token, "$argon2"):
        assert secret not in dumped
    assert not any(h in dumped for h in hashes)
    assert email  # người dùng thật đã được tạo qua API


def test_login_events_go_to_auth_events_not_audit_log(api: Api) -> None:
    user_id, email = api.create_user("engineer")
    before = len(_entries(api, user_id))
    client = api.client()
    login(client, email, "sai-mat-khau-roi")
    ok(login(client, email))
    ok(post(client, "/auth/logout"))
    with Session(api.engine) as session:
        kinds = list(
            session.scalars(
                select(m.AuthEvent.kind)
                .where(m.AuthEvent.email == email)
                .order_by(m.AuthEvent.created_at)
            )
        )
        login_rows = session.scalar(
            select(func.count()).select_from(m.AuditLog).where(m.AuditLog.action.like("%login%"))
        )
    assert kinds == ["login_failed", "login_success", "logout"]
    assert len(_entries(api, user_id)) == before
    assert login_rows == 0


def _pages(client: TestClient, params: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    cursor = None
    while True:
        page = ok(client.get("/audit-log", params=params | ({"cursor": cursor} if cursor else {})))
        body = page.json()
        items += body["items"]
        cursor = body["next_cursor"]
        if cursor is None:
            return items


def test_filters_and_pagination(api: Api) -> None:
    second_id, second_email = api.create_user("admin")
    second = api.client()
    ok(login(second, second_email))
    targets = []
    for _ in range(3):
        target, _ = api.create_user("engineer", status="pending")
        ok(post(second, f"/admin/users/{target}/approve", {"roles": ["engineer"]}))
        targets.append(target)
    # Người thứ hai cũng là actor của `user.access_requested` của chính mình: lọc thêm theo action.
    everything = _pages(second, {"actor_id": str(second_id), "limit": 2})
    assert {i["action"] for i in everything} == {"user.access_requested", "user.approved"}
    by_actor = _pages(second, {"actor_id": str(second_id), "action": "user.approved", "limit": 2})
    assert [uuid.UUID(i["entity_id"]) for i in by_actor] == list(reversed(targets))
    assert len({i["id"] for i in by_actor}) == len(by_actor)

    by_action = _pages(second, {"action": "user.approved", "entity_id": str(targets[0])})
    assert len(by_action) == 1

    newest = by_actor[0]["created_at"]
    since = _pages(second, {"actor_id": str(second_id), "since": newest})
    assert len(everything) == 4
    assert by_actor[0]["id"] in {i["id"] for i in since}
    until = _pages(second, {"actor_id": str(second_id), "until": newest})
    assert by_actor[0]["id"] not in {i["id"] for i in until}
    past = (api.clock() - timedelta(days=3650)).isoformat()
    assert _pages(second, {"actor_id": str(second_id), "until": past}) == []


@pytest.mark.parametrize("role", ["engineer", "reviewer"])
def test_without_audit_read_is_403(api: Api, role: str) -> None:
    _, _, client = api.logged_in(role)
    assert error(client.get("/audit-log")) == (403, "forbidden")


def test_unfiltered_audit_log_reads_rows_outside_convention(api: Api) -> None:
    with Session(api.engine) as session, session.begin():
        session.add(m.AuditLog(actor_id=None, action="x", entity_type="user"))
    response = api.admin().get("/audit-log", params={"limit": 5})
    assert response.status_code == 200
    assert "x" in {i["action"] for i in response.json()["items"]}
