"""validation.md Phase 4, Bảo vệ endpoint (`test_route_protection.py`)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from advertest_contracts.enums import Role
from advertest_contracts.permissions import ROLE_PERMISSIONS, Permission
from advertest_contracts.registry import SCHEMAS
from backend.app.main import create_app

from .conftest import REPO, Api, csrf, error

pytestmark = pytest.mark.db
OPENAPI: dict[str, Any] = json.loads((REPO / "contracts" / "openapi.json").read_text())
PUBLIC = {
    "/health",
    "/auth/request-access",
    "/auth/login",
    "/auth/password-reset",
    "/verify/{report_id}",
}
SAMPLE_ID = "00000000-0000-5000-8000-000000000001"
MOCKS = Path(REPO / "contracts" / "mocks")


def _body(op: dict[str, Any]) -> Any:
    if "requestBody" not in op:
        return None
    ref = op["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    name = re.sub(r"-(Input|Output)$", "", ref.rsplit("/", 1)[-1])
    mock_dir = next(d for d, model in SCHEMAS.items() if model.__name__ == name)
    return json.loads(sorted((MOCKS / mock_dir).glob("*.json"))[0].read_text())


PROTECTED = [
    (method, path, op)
    for path, ops in sorted(OPENAPI["paths"].items())
    for method, op in ops.items()
    if path not in PUBLIC and not path.startswith("/internal/worker")
]


def _url(path: str) -> str:
    return re.sub(r"\{[^}]+\}", SAMPLE_ID, path)


@pytest.mark.parametrize(("method", "path", "op"), PROTECTED, ids=lambda v: str(v)[:40])
def test_protected_route_is_401_without_session(
    api: Api, method: str, path: str, op: dict[str, Any]
) -> None:
    response = api.client().request(method, _url(path), json=_body(op))
    assert error(response) == (401, "unauthenticated")


def test_every_protected_route_declares_x_permission() -> None:
    allowed = {p.value for p in Permission} | {"authenticated"}
    # 23 route cần phiên ở Phase 4 (auth, admin, audit và các nhóm khung); con số chỉ để chắc
    # danh sách không rỗng do đọc sai OpenAPI.
    assert len(PROTECTED) >= 20
    for method, path, op in PROTECTED:
        assert op.get("x-permission") in allowed, (method, path)


def test_app_refuses_to_start_with_undeclared_route() -> None:
    app = create_app()
    extra = APIRouter()

    @extra.get("/route-gia-khong-khai-bao")
    def fake() -> None: ...

    app.include_router(extra)
    with pytest.raises(RuntimeError, match="route-gia-khong-khai-bao"), TestClient(app):
        pass


def _representatives() -> dict[Permission, tuple[str, str, Any]]:
    found: dict[Permission, tuple[str, str, Any]] = {}
    for method, path, op in PROTECTED:
        value = op.get("x-permission")
        if value and value != "authenticated" and Permission(value) not in found:
            found[Permission(value)] = (method, _url(path), _body(op))
    return found


REPRESENTATIVES = _representatives()


@pytest.mark.parametrize("role", list(Role))
def test_single_role_matches_matrix(api: Api, role: Role) -> None:
    _, _, client = api.logged_in(role.value)
    for permission, (method, path, body) in REPRESENTATIVES.items():
        response = client.request(method, path, json=body, headers=csrf(client))
        if permission in ROLE_PERMISSIONS[role]:
            assert response.status_code not in (401, 403), (role, permission, response.text)
        else:
            assert error(response) == (403, "forbidden"), (role, permission)


def test_multiple_roles_get_the_union(api: Api) -> None:
    _, _, client = api.logged_in("engineer", "reviewer")
    me = client.get("/auth/me").json()
    expected = ROLE_PERMISSIONS[Role.ENGINEER] | ROLE_PERMISSIONS[Role.REVIEWER]
    assert set(me["permissions"]) == {p.value for p in expected}
    # Phase 5 Group 2: POST /experiments đã cài đặt; body mẫu trỏ tới tài nguyên không có nên
    # route trả 422 invalid_request, tức đã qua kiểm tra quyền. Phase 8 Group 2: review.decide đã
    # cài đặt (GET /reviews trả hàng đợi, 200; người dùng cho phép sửa, 2026-10-02).
    method, path, body = REPRESENTATIVES[Permission.EXPERIMENT_CREATE]
    response = client.request(method, path, json=body, headers=csrf(client))
    assert error(response) == (422, "invalid_request")
    method, path, body = REPRESENTATIVES[Permission.REVIEW_DECIDE]
    assert client.request(method, path, json=body, headers=csrf(client)).status_code == 200
    method, path, body = REPRESENTATIVES[Permission.AUDIT_READ]
    assert error(client.request(method, path, json=body)) == (403, "forbidden")
