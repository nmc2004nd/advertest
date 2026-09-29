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
    # Phase 5: chỉ lỗi 422 được kèm `fields` (đường dẫn từng trường sai); lỗi khác đúng hai khóa.
    allowed = {"code", "message", "fields"} if response.status_code == 422 else {"code", "message"}
    assert response.json()["error"].keys() <= allowed
    assert {"code", "message"} <= response.json()["error"].keys()
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
    # Không lặp lại giá trị gửi lên ở bất kỳ đâu trong body (kể cả `fields`, Phase 5).
    assert secret[:5] not in response.text
    fields = ErrorResponse.model_validate(response.json()).error.fields
    assert fields is not None and [f.path for f in fields] == ["password"]


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
    # Route công khai: route cần phiên trả 401 trước khi xét tham số.
    response = client.get("/verify/khong-phai-uuid")
    assert _error(response)[:2] == (422, "validation_error")
