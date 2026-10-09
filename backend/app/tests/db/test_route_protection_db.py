"""Phân quyền với phiên thật (validation.md Phase 4: test_route_protection, phần đổi role của
test_immediate_effect). Mỗi permission đang có route được gọi qua một route đại diện."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session

from advertest_contracts.enums import Role
from advertest_contracts.models import ErrorResponse
from advertest_contracts.permissions import ROLE_PERMISSIONS, Permission
from advertest_contracts.registry import SCHEMAS
from backend.app.auth.sessions import CSRF_COOKIE, CSRF_HEADER
from backend.app.db import models as m
from backend.app.main import create_app

from .test_auth_api import Env, _login, _user, env  # fixture dùng chung

pytestmark = pytest.mark.db
__all__ = ["env"]
SAMPLE_ID = "00000000-0000-5000-8000-000000000001"
MOCKS = Path(__file__).resolve().parents[4] / "contracts" / "mocks"
OPENAPI = create_app().openapi()


def _body(op: dict[str, Any]) -> Any:
    # Phase R2: POST /quick-tries nhận multipart, không có body JSON mẫu (quyền kiểm tra trước).
    if "application/json" not in op.get("requestBody", {}).get("content", {}):
        return None
    ref = op["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    name = re.sub(r"-(Input|Output)$", "", ref.rsplit("/", 1)[-1])
    mock_dir = next(d for d, model in SCHEMAS.items() if model.__name__ == name)
    return json.loads(sorted((MOCKS / mock_dir).glob("*.json"))[0].read_text())


def _representatives() -> dict[Permission, tuple[str, str, Any]]:
    """Một route (method, path, body) cho mỗi permission có route; ưu tiên route còn là khung
    (trả 501 khi được phép, không cần dữ liệu)."""
    found: dict[Permission, tuple[str, str, Any]] = {}
    for path, ops in sorted(OPENAPI["paths"].items()):
        for method, op in ops.items():
            value = op.get("x-permission")
            if value is None or value == "authenticated" or Permission(value) in found:
                continue
            found[Permission(value)] = (
                method,
                re.sub(r"\{[^}]+\}", SAMPLE_ID, path),
                _body(op),
            )
    return found


REPRESENTATIVES = _representatives()


def _call(client: TestClient, permission: Permission) -> tuple[int, str]:
    method, path, body = REPRESENTATIVES[permission]
    headers = {CSRF_HEADER: client.cookies.get(CSRF_COOKIE) or ""}
    response = client.request(method, path, json=body, headers=headers)
    if response.status_code < 400:
        return response.status_code, ""
    return response.status_code, ErrorResponse.model_validate(response.json()).error.code


@pytest.mark.parametrize("role", list(Role))
def test_each_role_gets_exactly_the_matrix(env: Env, role: Role) -> None:
    _, email = _user(env.engine, roles=(role,))
    client = env.client()
    assert _login(client, email).status_code == 200
    for permission in REPRESENTATIVES:
        status, code = _call(client, permission)
        if permission in ROLE_PERMISSIONS[role]:
            # Được phép: qua kiểm tra quyền, tới route (khung 501 hoặc kết quả thật).
            assert status not in (401, 403), (role, permission, status, code)
        else:
            assert (status, code) == (403, "forbidden"), (role, permission)


def test_union_of_roles(env: Env) -> None:
    _, email = _user(env.engine, roles=(Role.ENGINEER, Role.REVIEWER))
    client = env.client()
    _login(client, email)
    # POST /experiments đã cài đặt (Phase 5 Group 2): body mẫu trỏ tới tài nguyên không có → 422
    # tại route, tức đã qua kiểm tra quyền.
    assert _call(client, Permission.EXPERIMENT_CREATE) == (422, "invalid_request")
    # Phase 8 Group 2: review.decide đã cài đặt (GET /reviews trả hàng đợi).
    assert _call(client, Permission.REVIEW_DECIDE)[0] == 200
    assert _call(client, Permission.AUDIT_READ) == (403, "forbidden")


def test_removing_a_role_takes_effect_on_the_next_request(env: Env) -> None:
    user_id, email = _user(env.engine, roles=(Role.ENGINEER, Role.REVIEWER))
    client = env.client()
    _login(client, email)
    assert _call(client, Permission.EXPERIMENT_CREATE) == (422, "invalid_request")
    with Session(env.engine) as session, session.begin():
        session.execute(
            delete(m.UserRole).where(
                m.UserRole.user_id == user_id, m.UserRole.role == Role.ENGINEER
            )
        )
    assert _call(client, Permission.EXPERIMENT_CREATE) == (403, "forbidden")
    assert client.get("/auth/me").json()["roles"] == ["reviewer"]


def test_every_permission_with_a_route_is_covered() -> None:
    # Permission chưa có route (Phase 6+) chỉ được kiểm tra ở mức ma trận (tests/auth).
    # Phase 5 Group 0 thêm route cho protocol.read và experiment.cancel_own: 12 → 14.
    assert {
        Permission.USER_MANAGE,
        Permission.AUDIT_READ,
        Permission.MODEL_READ,
        Permission.PROTOCOL_READ,
        Permission.EXPERIMENT_CANCEL_OWN,
    } <= set(REPRESENTATIVES)
    # Phase 6: attack_catalog.manage (/admin/attack-specs). Phase 8 Group 0:
    # experiment.submit_review, review.comment, report.export. Phase R2 Group 0:
    # attack_catalog.approve, quick_try.use, model.manage (POST /models).
    assert len(REPRESENTATIVES) == 21
