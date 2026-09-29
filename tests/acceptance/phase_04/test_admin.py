"""validation.md Phase 4, Quản trị (`test_admin.py`)."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from advertest_contracts.enums import Role, UserStatus
from backend.app.db import models as m

from .conftest import (
    ADMIN_EMAIL,
    NEW_PASSWORD,
    Api,
    error,
    login,
    ok,
    post,
    put,
)

pytestmark = pytest.mark.db


def test_approve_requires_a_role_and_roles_cannot_be_emptied(api: Api) -> None:
    admin = api.admin()
    pending, _ = api.create_user("engineer", status="pending")
    assert error(post(admin, f"/admin/users/{pending}/approve", {"roles": []})) == (
        422,
        "validation_error",
    )
    active, _ = api.create_user("engineer")
    assert error(put(admin, f"/admin/users/{active}/roles", {"roles": []})) == (
        422,
        "validation_error",
    )


def test_approve_activates_with_roles_and_user_can_log_in(api: Api) -> None:
    user_id, email = api.create_user("engineer", status="pending")
    view = ok(post(api.admin(), f"/admin/users/{user_id}/approve", {"roles": ["engineer"]})).json()
    assert (view["status"], view["roles"]) == ("active", ["engineer"])
    assert login(api.client(), email).status_code == 200


def test_reject_requires_reason_and_stores_it(api: Api) -> None:
    admin = api.admin()
    user_id, _ = api.create_user("engineer", status="pending")
    assert error(post(admin, f"/admin/users/{user_id}/reject", {"reason": ""})) == (
        422,
        "validation_error",
    )
    view = ok(post(admin, f"/admin/users/{user_id}/reject", {"reason": "Không thuộc nhóm"})).json()
    assert (view["status"], view["reject_reason"]) == ("rejected", "Không thuộc nhóm")


def _admin_id(api: Api) -> uuid.UUID:
    return api.user_id(ADMIN_EMAIL)


def test_admin_cannot_disable_themself(api: Api) -> None:
    assert error(post(api.admin(), f"/admin/users/{_admin_id(api)}/disable")) == (409, "conflict")


@pytest.fixture
def only_seed_admin_active(api: Api) -> Iterator[None]:
    """Tạm vô hiệu mọi admin active khác (DB dùng chung với test khác), khôi phục sau test."""
    seed_admin = _admin_id(api)
    with Session(api.engine) as session, session.begin():
        others = list(
            session.scalars(
                select(m.User.id)
                .join(m.UserRole, m.UserRole.user_id == m.User.id)
                .where(
                    m.UserRole.role == Role.ADMIN,
                    m.User.status == UserStatus.ACTIVE,
                    m.User.id != seed_admin,
                )
            )
        )
        if others:
            session.execute(
                update(m.User).where(m.User.id.in_(others)).values(status=UserStatus.DISABLED)
            )
    try:
        yield
    finally:
        if others:
            with Session(api.engine) as session, session.begin():
                session.execute(
                    update(m.User).where(m.User.id.in_(others)).values(status=UserStatus.ACTIVE)
                )


@pytest.mark.usefixtures("only_seed_admin_active")
def test_last_active_admin_keeps_admin_role(api: Api) -> None:
    seed_admin = _admin_id(api)
    admin = api.admin()
    # Admin active cuối cùng không bỏ được role admin của chính mình, và không tự vô hiệu hóa.
    assert error(put(admin, f"/admin/users/{seed_admin}/roles", {"roles": ["engineer"]})) == (
        409,
        "conflict",
    )
    assert error(post(admin, f"/admin/users/{seed_admin}/disable")) == (409, "conflict")
    # Có thêm một admin active: người thứ hai bỏ được role admin của admin seed, và khi đó chính
    # người thứ hai thành admin active cuối cùng nên không bỏ được role admin của mình.
    second_id, second_email = api.create_user("admin")
    second = api.client()
    ok(login(second, second_email))
    ok(put(second, f"/admin/users/{seed_admin}/roles", {"roles": ["engineer"]}))
    assert error(put(second, f"/admin/users/{second_id}/roles", {"roles": ["reviewer"]})) == (
        409,
        "conflict",
    )
    # Trả lại trạng thái cho các test khác: admin seed có lại role admin, người thứ hai bị vô hiệu.
    ok(put(second, f"/admin/users/{seed_admin}/roles", {"roles": ["admin"]}))
    ok(post(api.admin(), f"/admin/users/{second_id}/disable"))


def _reset_token(api: Api, admin: TestClient, user_id: uuid.UUID) -> str:
    link: dict[str, Any] = ok(post(admin, f"/admin/users/{user_id}/reset-link")).json()
    assert link["url"].startswith("http://reset.phase04.test/reset-password/")
    return str(link["url"]).rsplit("/", 1)[1]


def test_reset_link_single_use_24h_revokes_sessions_and_replaces_old(
    api: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP_BASE_URL", "http://reset.phase04.test")
    admin = api.admin()
    user_id, email, logged_in = api.logged_in("engineer")
    old = _reset_token(api, admin, user_id)
    token = _reset_token(api, admin, user_id)
    body = {"token": old, "new_password": NEW_PASSWORD}
    assert error(api.client().post("/auth/password-reset", json=body)) == (422, "invalid_request")
    body = {"token": token, "new_password": NEW_PASSWORD}
    assert api.client().post("/auth/password-reset", json=body).status_code == 204
    assert error(api.client().post("/auth/password-reset", json=body)) == (422, "invalid_request")
    assert error(logged_in.get("/auth/me")) == (401, "unauthenticated")
    assert login(api.client(), email, NEW_PASSWORD).status_code == 200

    expiring = _reset_token(api, admin, user_id)
    api.clock.advance(hours=24)
    body = {"token": expiring, "new_password": "mat-khau-thu-ba-3"}
    assert error(api.client().post("/auth/password-reset", json=body)) == (422, "invalid_request")


@pytest.mark.parametrize("role", ["engineer", "reviewer"])
def test_without_user_manage_is_403(api: Api, role: str) -> None:
    target, _ = api.create_user("engineer")
    _, _, client = api.logged_in(role)
    assert error(client.get("/admin/users")) == (403, "forbidden")
    for action in ("disable", "enable", "reset-link"):
        assert error(post(client, f"/admin/users/{target}/{action}")) == (403, "forbidden")
    assert error(put(client, f"/admin/users/{target}/roles", {"roles": ["admin"]})) == (
        403,
        "forbidden",
    )


def test_invalid_transitions_are_conflicts(api: Api) -> None:
    admin = api.admin()
    active, _ = api.create_user("engineer")
    disabled, _ = api.create_user("engineer", status="disabled")
    pending, _ = api.create_user("engineer", status="pending")
    rejected, _ = api.create_user("engineer", status="rejected")
    cases = [
        post(admin, f"/admin/users/{active}/approve", {"roles": ["engineer"]}),
        post(admin, f"/admin/users/{active}/enable"),
        post(admin, f"/admin/users/{disabled}/disable"),
        put(admin, f"/admin/users/{pending}/roles", {"roles": ["engineer"]}),
        put(admin, f"/admin/users/{rejected}/roles", {"roles": ["engineer"]}),
        post(admin, f"/admin/users/{pending}/reset-link"),
        post(admin, f"/admin/users/{rejected}/reset-link"),
    ]
    assert [error(r) for r in cases] == [(409, "conflict")] * len(cases)


def test_pending_list_filters_and_pages_without_gaps(api: Api) -> None:
    created = {api.create_user("engineer", status="pending")[0] for _ in range(5)}
    admin = api.admin()
    seen: list[dict[str, Any]] = []
    cursor = None
    while True:
        params = {"status": "pending", "limit": 2} | ({"cursor": cursor} if cursor else {})
        page = ok(admin.get("/admin/users", params=params)).json()
        seen += page["items"]
        cursor = page["next_cursor"]
        if cursor is None:
            break
    ids = [uuid.UUID(u["id"]) for u in seen]
    assert len(ids) == len(set(ids))
    assert created <= set(ids)
    assert {u["status"] for u in seen} == {"pending"}
