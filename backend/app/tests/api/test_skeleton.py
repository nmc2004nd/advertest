"""Khung API: đủ nhóm endpoint, security scheme đúng, endpoint chưa làm trả 501."""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from advertest_contracts.enums import ErrorCode, Role, UserStatus
from advertest_contracts.models import ErrorResponse, FieldError
from advertest_contracts.permissions import AUTHENTICATED, Permission
from backend.app.api.deps import get_sessionmaker
from backend.app.api.errors import ApiError
from backend.app.auth.deps import Principal, current_user
from backend.app.main import create_app

PUBLIC_GROUPS = [
    "/auth", "/admin", "/models", "/datasets", "/slices", "/attack-specs", "/protocols",
    "/experiments", "/runs", "/failure-cases", "/reviews", "/reports", "/compute-targets",
    "/budget", "/audit-log", "/verify",
]  # fmt: skip
WORKER_ENDPOINTS = {
    ("post", "/internal/worker/lease"),
    ("post", "/internal/worker/heartbeat"),
    ("post", "/internal/worker/runs/{run_id}/progress"),
    ("post", "/internal/worker/runs/{run_id}/artifact-url"),
    ("post", "/internal/worker/runs/{run_id}/complete"),
    ("post", "/internal/worker/experiments/{experiment_id}/search-result"),
    ("get", "/internal/worker/experiments/{experiment_id}/bundle"),
    ("post", "/internal/worker/runs/{run_id}/start"),
    ("post", "/internal/worker/cost-profiles"),
    # Phase 6: dừng sớm, đăng ký patch.
    ("post", "/internal/worker/runs/{run_id}/skip"),
    ("post", "/internal/worker/runs/{run_id}/patch"),
    # Phase 7: tạo run động của tìm ngưỡng.
    ("post", "/internal/worker/experiments/{experiment_id}/runs"),
}
RUN_ID = "00000000-0000-5000-8000-000000000001"
# Endpoint xác thực công khai (requirements.md Phase 4, mục Bảo vệ endpoint).
PUBLIC_AUTH_PATHS = {"/auth/request-access", "/auth/login", "/auth/password-reset"}
# Phase 5 Group 1 cài đặt API đọc tài nguyên (/models, /datasets, /dataset-versions, /slices,
# /class-mappings, /attack-specs, GET /protocols, /compute-targets): test với DB ở
# tests/db/test_catalog_api.py.
# Phase 5 Group 2 cài đặt experiment, run, failure case, ảnh: test với DB ở
# tests/db/test_experiment_api.py, test_failure_case_api.py.
# Phase 8 Group 1 cài đặt /protocols* (tests/db/test_phase08_protocols.py), Group 2 cài đặt
# /reviews* (tests/db/test_phase08_reviews.py), Group 3 cài đặt /reports*, /verify
# (tests/db/test_phase08_reports.py). Còn /budget (Phase 9).
SAMPLE_CALLS = [
    ("get", "/budget"),
]
# Endpoint có body bắt buộc: gửi body hợp lệ lấy từ contracts/mocks.
MOCKS = Path(__file__).resolve().parents[4] / "contracts" / "mocks"
BODIES = {
    "/internal/worker/heartbeat": "heartbeat_request/default.json",
    "/internal/worker/runs/" + RUN_ID + "/artifact-url": "artifact_url_request/put_candidate.json",
    "/internal/worker/runs/" + RUN_ID + "/start": "run_start_request/gpu_local.json",
    "/internal/worker/runs/" + RUN_ID + "/progress": "progress_report/after_batch_0.json",
    "/internal/worker/runs/" + RUN_ID + "/complete": "run_completion/completed_one_case.json",
    "/internal/worker/cost-profiles": "cost_profile/gpu_local_pgd.json",
    "/internal/worker/experiments/"
    + RUN_ID
    + "/search-result": "search_result_report/final_found.json",
    "/internal/worker/experiments/" + RUN_ID + "/runs": "search_run_create/subset_coarse.json",
    "/internal/worker/runs/" + RUN_ID + "/skip": "run_skip_request/early_stop.json",
    "/internal/worker/runs/" + RUN_ID + "/patch": "patch_registration/trained_0.25.json",
}
# Endpoint worker đã cài đặt (Phase 3): thiếu token → 401, không cần DB.
IMPLEMENTED_WORKER_CALLS = [
    ("post", "/internal/worker/lease"),
    ("get", "/internal/worker/experiments/" + RUN_ID + "/bundle"),
    ("post", "/internal/worker/heartbeat"),
    ("post", "/internal/worker/runs/" + RUN_ID + "/start"),
    ("post", "/internal/worker/runs/" + RUN_ID + "/progress"),
    ("post", "/internal/worker/runs/" + RUN_ID + "/artifact-url"),
    ("post", "/internal/worker/runs/" + RUN_ID + "/complete"),
    ("post", "/internal/worker/cost-profiles"),
    # Phase 6 Group 5.
    ("post", "/internal/worker/runs/" + RUN_ID + "/skip"),
    ("post", "/internal/worker/runs/" + RUN_ID + "/patch"),
    # Phase 7 Group 4: tạo run động, SearchResult.
    ("post", "/internal/worker/experiments/" + RUN_ID + "/runs"),
    ("post", "/internal/worker/experiments/" + RUN_ID + "/search-result"),
]


@pytest.fixture(scope="module")
def openapi() -> dict[str, Any]:
    return create_app().openapi()


def test_every_public_group_has_an_endpoint(openapi: dict[str, Any]) -> None:
    paths = openapi["paths"]
    for group in PUBLIC_GROUPS:
        assert any(p == group or p.startswith(group + "/") for p in paths), group


def test_worker_endpoints(openapi: dict[str, Any]) -> None:
    declared = {
        (method, path)
        for path, ops in openapi["paths"].items()
        if path.startswith("/internal/worker")
        for method in ops
    }
    assert declared == WORKER_ENDPOINTS


def test_security_schemes(openapi: dict[str, Any]) -> None:
    schemes = openapi["components"]["securitySchemes"]
    assert schemes["userSession"] == {
        "type": "apiKey", "in": "cookie", "name": "advertest_session",
        "description": (
            "Cookie phiên của người dùng (token ngẫu nhiên, httpOnly; phiên lưu phía server)."
        ),
    }  # fmt: skip
    assert schemes["workerToken"]["type"] == "http"
    assert schemes["workerToken"]["scheme"] == "bearer"
    for path, ops in openapi["paths"].items():
        for op in ops.values():
            names = {name for req in op.get("security", []) for name in req}
            if path.startswith("/internal/worker"):
                assert names == {"workerToken"}, path
            elif path.startswith(("/verify", "/health")) or path in PUBLIC_AUTH_PATHS:
                assert names == set(), path
            else:
                assert names == {"userSession"}, path


def _client(*, as_user: Principal | None = None) -> TestClient:
    """App không cần DB: thiếu phiên bị từ chối trước khi mở DB; `as_user` thay current_user."""
    app = create_app()
    app.dependency_overrides[get_sessionmaker] = lambda: sessionmaker()
    if as_user is not None:
        app.dependency_overrides[current_user] = lambda: as_user
    return TestClient(app)


ALL_ROLES = Principal(
    user_id=uuid.uuid4(),
    session_id=uuid.uuid4(),
    email="all@x.test",
    full_name="Đủ role",
    status=UserStatus.ACTIVE,
    roles=frozenset(Role),
)


@pytest.mark.parametrize(("method", "path"), SAMPLE_CALLS)
def test_unimplemented_endpoints_return_501_error_body(method: str, path: str) -> None:
    body = json.loads((MOCKS / BODIES[path]).read_text()) if path in BODIES else None
    # Phase 4: route cần phiên kiểm tra quyền trước 501; người dùng giả có đủ 3 role.
    response = _client(as_user=ALL_ROLES).request(method, path, json=body)
    assert response.status_code == 501
    body = ErrorResponse.model_validate(response.json())
    assert body.error.code == "not_implemented"
    assert response.json()["error"].keys() == {"code", "message"}


def test_openapi_declares_501_with_error_response(openapi: dict[str, Any]) -> None:
    for path, ops in openapi["paths"].items():
        if path == "/health":
            continue
        for method, op in ops.items():
            schema = op["responses"]["501"]["content"]["application/json"]["schema"]
            assert schema == {"$ref": "#/components/schemas/ErrorResponse"}, (method, path)


@pytest.mark.parametrize(("method", "path"), IMPLEMENTED_WORKER_CALLS)
def test_worker_endpoints_require_token(method: str, path: str) -> None:
    body = json.loads((MOCKS / BODIES[path]).read_text()) if path in BODIES else None
    client = TestClient(create_app())
    for headers in ({}, {"Authorization": "Bearer "}):
        response = client.request(method, path, json=body, headers=headers)
        assert response.status_code == 401
        assert ErrorResponse.model_validate(response.json()).error.code == "unauthenticated"


def test_every_session_route_declares_a_valid_permission(openapi: dict[str, Any]) -> None:
    allowed = {p.value for p in Permission} | {AUTHENTICATED}
    for path, ops in openapi["paths"].items():
        for method, op in ops.items():
            names = {name for req in op.get("security", []) for name in req}
            if names == {"userSession"}:
                assert op.get("x-permission") in allowed, (method, path)
                assert {"401", "403"} <= set(op["responses"]), (method, path)
            else:
                assert "x-permission" not in op, (method, path)


def _session_routes(openapi: dict[str, Any]) -> list[tuple[str, str]]:
    return [
        (method, re.sub(r"\{[^}]+\}", RUN_ID, path))
        for path, ops in openapi["paths"].items()
        for method, op in ops.items()
        if {name for req in op.get("security", []) for name in req} == {"userSession"}
    ]


def test_every_session_route_rejects_missing_session_before_501(openapi: dict[str, Any]) -> None:
    routes = _session_routes(openapi)
    assert len(routes) >= 20
    client = _client()
    for method, path in routes:
        response = client.request(method, path)
        assert response.status_code == 401, (method, path)
        assert ErrorResponse.model_validate(response.json()).error.code == "unauthenticated"


def test_missing_permission_is_403_before_501() -> None:
    engineer = Principal(
        user_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        email="e@x.test",
        full_name="Engineer",
        status=UserStatus.ACTIVE,
        roles=frozenset({Role.ENGINEER}),
    )
    response = _client(as_user=engineer).get("/audit-log")
    assert response.status_code == 403
    assert ErrorResponse.model_validate(response.json()).error.code == "forbidden"


# ---------------------------------------------------------------- lỗi chung (Phase 5, task 1a)


def test_openapi_declares_422_as_error_response(openapi: dict[str, Any]) -> None:
    """Mọi route có tham số hoặc body (kể cả API nội bộ của worker, Phase 5 task 5a) khai 422 là
    ErrorResponse, không phải HTTPValidationError mặc định của FastAPI."""
    checked = 0
    for path, ops in openapi["paths"].items():
        for method, op in ops.items():
            if "422" not in op["responses"]:
                continue
            schema = op["responses"]["422"]["content"]["application/json"]["schema"]
            assert schema == {"$ref": "#/components/schemas/ErrorResponse"}, (method, path)
            checked += 1
    assert checked >= 28
    assert "HTTPValidationError" not in openapi["components"]["schemas"]


def test_unhandled_exception_is_internal_error_without_details() -> None:
    app = create_app()

    @app.get("/loi-bat-ngo")
    def boom() -> None:
        raise RuntimeError("postgres://advertest:mat-khau@db/advertest")

    response = TestClient(app, raise_server_exceptions=False).get("/loi-bat-ngo")
    assert response.status_code == 500
    body = ErrorResponse.model_validate(response.json())
    assert body.error.code == "internal_error"
    assert "mat-khau" not in response.text
    assert response.json()["error"].keys() == {"code", "message"}


def test_api_error_fields_are_returned_only_when_present() -> None:
    app = create_app()
    fields = [FieldError(path="attacks.0.grid.levels", message="Ngoài dải")]

    @app.get("/loi-co-truong")
    def with_fields() -> None:
        raise ApiError(422, ErrorCode.INVALID_REQUEST, "Cấu hình không hợp lệ", fields)

    response = TestClient(app).get("/loi-co-truong")
    assert response.status_code == 422
    body = ErrorResponse.model_validate(response.json())
    assert body.error.fields == fields
