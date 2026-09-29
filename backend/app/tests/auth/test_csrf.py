"""CSRF (validation.md Phase 4, test_csrf): không cần DB vì middleware chặn trước route."""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from advertest_contracts.models import ErrorResponse
from backend.app.api.deps import get_sessionmaker
from backend.app.api.security import SESSION_COOKIE
from backend.app.auth.sessions import CSRF_COOKIE, CSRF_HEADER
from backend.app.main import create_app

MUTATING = [("post", "/auth/logout"), ("post", "/auth/password"), ("post", "/experiments")]


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    # Request qua được middleware nhưng bị từ chối trước khi dùng DB (body sai, thiếu phiên).
    app.dependency_overrides[get_sessionmaker] = lambda: sessionmaker()
    return TestClient(app)


def _is_csrf_failure(response: httpx.Response) -> bool:
    if response.status_code != 403:
        return False
    return ErrorResponse.model_validate(response.json()).error.code == "csrf_failed"


@pytest.mark.parametrize(("method", "path"), MUTATING)
def test_missing_header_with_session_cookie_is_rejected(
    client: TestClient, method: str, path: str
) -> None:
    client.cookies.set(SESSION_COOKIE, "phien")
    client.cookies.set(CSRF_COOKIE, "abc")
    assert _is_csrf_failure(client.request(method, path, json={}))


@pytest.mark.parametrize(("method", "path"), MUTATING)
def test_mismatched_header_is_rejected(client: TestClient, method: str, path: str) -> None:
    client.cookies.set(SESSION_COOKIE, "phien")
    client.cookies.set(CSRF_COOKIE, "abc")
    response = client.request(method, path, json={}, headers={CSRF_HEADER: "xyz"})
    assert _is_csrf_failure(response)


def test_header_without_csrf_cookie_is_rejected(client: TestClient) -> None:
    client.cookies.set(SESSION_COOKIE, "phien")
    assert _is_csrf_failure(client.post("/auth/logout", headers={CSRF_HEADER: ""}))


def test_matching_header_passes_the_middleware(client: TestClient) -> None:
    client.cookies.set(SESSION_COOKIE, "phien")
    client.cookies.set(CSRF_COOKIE, "abc")
    response = client.post("/experiments", json={}, headers={CSRF_HEADER: "abc"})
    assert not _is_csrf_failure(response)


def test_get_does_not_need_csrf(client: TestClient) -> None:
    client.cookies.set(SESSION_COOKIE, "phien")
    assert not _is_csrf_failure(client.get("/models"))


def test_post_without_session_cookie_does_not_need_csrf(client: TestClient) -> None:
    assert not _is_csrf_failure(client.post("/auth/login", json={}))


def test_worker_endpoints_are_exempt(client: TestClient) -> None:
    client.cookies.set(SESSION_COOKIE, "phien")
    # Endpoint worker còn là khung (không cần DB): tới được route nghĩa là middleware bỏ qua.
    response = client.post(
        "/internal/worker/experiments/00000000-0000-5000-8000-000000000001/search-result",
        json={},
        headers={"Authorization": "Bearer sai"},
    )
    assert not _is_csrf_failure(response)
