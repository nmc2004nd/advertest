"""Định dạng lỗi thống nhất (requirements.md Phase 4: mọi lỗi trả ErrorResponse; 422 do body
sai schema là `validation_error` thay body mặc định {"detail": ...} của FastAPI)."""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from advertest_contracts.models import ErrorResponse
from backend.app.api.deps import get_sessionmaker
from backend.app.main import create_app


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    # Body sai bị từ chối trước khi dùng DB; factory giả để không cần DATABASE_URL.
    app.dependency_overrides[get_sessionmaker] = lambda: sessionmaker()
    return TestClient(app)


def _error(response: httpx.Response) -> tuple[int, str, str]:
    body = ErrorResponse.model_validate(response.json())
    assert response.json()["error"].keys() == {"code", "message"}
    return response.status_code, body.error.code, body.error.message


def test_body_schema_error_is_validation_error_without_echoing_input(client: TestClient) -> None:
    secret = "mat-khau-bi-mat"
    response = client.post(
        "/auth/request-access",
        json={
            "full_name": "A",
            "email": "a@x.com",
            "requested_role": "engineer",
            "reason": "r",
            "password": secret[:5],
        },
    )
    status, code, message = _error(response)
    assert (status, code) == (422, "validation_error")
    assert "password" in message
    assert secret[:5] not in message


def test_password_equal_to_email_is_validation_error(client: TestClient) -> None:
    response = client.post(
        "/auth/request-access",
        json={
            "full_name": "A",
            "email": "abcdefgh@x.com",
            "requested_role": "engineer",
            "reason": "r",
            "password": "ABCDEFGH@x.com",
        },
    )
    status, code, message = _error(response)
    assert (status, code) == (422, "validation_error")
    assert "trùng email" in message


def test_unknown_route_and_method_use_error_response(client: TestClient) -> None:
    assert _error(client.get("/khong-ton-tai"))[:2] == (404, "not_found")
    response = client.get("/auth/login")
    assert _error(response)[:2] == (405, "invalid_request")
    assert "POST" in response.headers["allow"]


def test_bad_query_parameter_is_validation_error(client: TestClient) -> None:
    response = client.get("/runs/khong-phai-uuid")
    assert _error(response)[:2] == (422, "validation_error")
