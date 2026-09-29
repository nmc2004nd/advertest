"""Khung API: đủ nhóm endpoint, security scheme đúng, endpoint chưa làm trả 501."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from advertest_contracts.models import ErrorResponse
from backend.app.main import create_app

PUBLIC_GROUPS = [
    "/auth", "/users", "/models", "/datasets", "/slices", "/attack-specs", "/protocols",
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
}
RUN_ID = "00000000-0000-5000-8000-000000000001"
SAMPLE_CALLS = [
    ("post", "/auth/login"),
    ("get", "/users"),
    ("get", "/models"),
    ("get", "/datasets"),
    ("get", "/slices"),
    ("get", "/attack-specs"),
    ("get", "/failure-cases/" + RUN_ID),
    ("get", "/runs/" + RUN_ID),
    ("get", "/reviews"),
    ("get", "/reports/" + RUN_ID),
    ("get", "/compute-targets"),
    ("get", "/budget"),
    ("get", "/audit-log"),
    ("get", "/verify/" + RUN_ID),
    # Endpoint worker còn là khung (Phase 7).
    ("post", "/internal/worker/experiments/" + RUN_ID + "/search-result"),
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
    "/internal/worker/experiments/" + RUN_ID + "/search-result": "search_result/found.json",
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
        "description": "Cookie phiên của người dùng (JWT, httpOnly).",
    }  # fmt: skip
    assert schemes["workerToken"]["type"] == "http"
    assert schemes["workerToken"]["scheme"] == "bearer"
    for path, ops in openapi["paths"].items():
        for op in ops.values():
            names = {name for req in op.get("security", []) for name in req}
            if path.startswith("/internal/worker"):
                assert names == {"workerToken"}, path
            elif path.startswith(("/verify", "/health")):
                assert names == set(), path
            else:
                assert names == {"userSession"}, path


@pytest.mark.parametrize(("method", "path"), SAMPLE_CALLS)
def test_unimplemented_endpoints_return_501_error_body(method: str, path: str) -> None:
    body = json.loads((MOCKS / BODIES[path]).read_text()) if path in BODIES else None
    response = TestClient(create_app()).request(method, path, json=body)
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
