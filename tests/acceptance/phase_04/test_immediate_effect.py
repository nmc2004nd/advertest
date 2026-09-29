"""validation.md Phase 4, Hiệu lực tức thời (`test_immediate_effect.py`)."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db import models as m

from .conftest import NEW_PASSWORD, PASSWORD, Api, error, login, ok, post, put

pytestmark = pytest.mark.db


def test_removing_engineer_role_is_403_on_next_request(api: Api) -> None:
    user_id, _, client = api.logged_in("engineer", "reviewer")
    assert post(client, "/experiments", {}).status_code != 403
    ok(put(api.admin(), f"/admin/users/{user_id}/roles", {"roles": ["reviewer"]}))
    assert error(post(client, "/experiments", {})) == (403, "forbidden")


def test_disabling_is_401_on_next_request_and_revokes_every_session(api: Api) -> None:
    user_id, email, client = api.logged_in("engineer")
    other = api.client()
    ok(login(other, email))
    ok(post(api.admin(), f"/admin/users/{user_id}/disable"))
    assert error(client.get("/auth/me")) == (401, "unauthenticated")
    assert error(other.get("/auth/me")) == (401, "unauthenticated")
    with Session(api.engine) as session:
        open_sessions = session.scalars(
            select(m.UserSession).where(
                m.UserSession.user_id == user_id, m.UserSession.revoked_at.is_(None)
            )
        ).all()
    assert open_sessions == []


def test_password_change_revokes_other_sessions_only(api: Api) -> None:
    _, email, current = api.logged_in("engineer")
    other = api.client()
    ok(login(other, email))
    ok(
        post(
            current, "/auth/password", {"current_password": PASSWORD, "new_password": NEW_PASSWORD}
        )
    )
    assert current.get("/auth/me").status_code == 200
    assert error(other.get("/auth/me")) == (401, "unauthenticated")


def test_wrong_current_password_is_422_and_keeps_session(api: Api) -> None:
    _, _, client = api.logged_in("engineer")
    response = post(
        client,
        "/auth/password",
        {"current_password": "sai-mat-khau-cu", "new_password": NEW_PASSWORD},
    )
    assert error(response) == (422, "invalid_request")
    assert client.get("/auth/me").status_code == 200
