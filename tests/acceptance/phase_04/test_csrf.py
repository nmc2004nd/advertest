"""validation.md Phase 4, CSRF (`test_csrf.py`)."""

from __future__ import annotations

import pytest

from .conftest import CSRF_HEADER, Api, error

pytestmark = pytest.mark.db


def test_post_without_csrf_header_is_rejected(api: Api) -> None:
    _, _, client = api.logged_in("engineer")
    assert error(client.post("/auth/logout")) == (403, "csrf_failed")


def test_mismatched_csrf_header_is_rejected(api: Api) -> None:
    _, _, client = api.logged_in("engineer")
    assert error(client.post("/auth/logout", headers={CSRF_HEADER: "khong-khop"})) == (
        403,
        "csrf_failed",
    )
    assert client.get("/auth/me").status_code == 200


def test_get_does_not_need_csrf(api: Api) -> None:
    _, _, client = api.logged_in("engineer")
    assert client.get("/auth/me").status_code == 200


def test_worker_endpoints_do_not_need_csrf(api: Api) -> None:
    """Có cookie phiên nhưng gọi API worker bằng bearer token: không bị chặn vì CSRF (401 là do
    token sai, không phải csrf_failed)."""
    _, _, client = api.logged_in("engineer")
    response = client.post("/internal/worker/lease", headers={"Authorization": "Bearer sai"})
    assert error(response) == (401, "unauthenticated")
