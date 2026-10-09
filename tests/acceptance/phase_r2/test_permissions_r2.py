"""validation.md Phase R2, Group 4 — Endpoint mới có `x-permission` đúng ma trận quyền (bổ sung test
ma trận Phase 4: `tests/acceptance/phase_04/test_route_protection.py` kiểm mọi route có
`x-permission` và từng role khớp ma trận). Không cần DB; đọc `contracts/openapi.json`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from advertest_contracts.enums import Role
from advertest_contracts.permissions import ROLE_PERMISSIONS, Permission

OPENAPI: dict[str, Any] = json.loads(
    (Path(__file__).resolve().parents[3] / "contracts" / "openapi.json").read_text()
)

EXPECTED = {
    ("get", "/experiments/{experiment_id}/insight"): "experiment.read",
    ("post", "/experiments/{experiment_id}/promote"): "experiment.create",
    ("post", "/experiments/draft"): "experiment.create",
    ("get", "/experiment-presets"): "experiment.read",
    ("get", "/protocol-templates"): "protocol.read",
    ("get", "/protocol-templates/{key}/draft"): "protocol.manage",
    ("get", "/attack-adapters"): "attack_catalog.manage",
    ("post", "/admin/attack-specs"): "attack_catalog.manage",
    ("post", "/admin/attack-specs/{spec_id}/check"): "attack_catalog.manage",
    ("patch", "/admin/attack-specs/{spec_id}/metadata"): "attack_catalog.manage",
    ("get", "/attack-specs/pending"): "attack_catalog.approve",
    ("post", "/attack-specs/{spec_id}/approve"): "attack_catalog.approve",
    ("post", "/attack-specs/{spec_id}/reject"): "attack_catalog.approve",
    ("post", "/models/uploads"): "model.manage",
    ("post", "/models"): "model.manage",
    ("post", "/quick-tries"): "quick_try.use",
    ("get", "/quick-tries/{quick_try_id}"): "quick_try.use",
}


@pytest.mark.parametrize(("method", "path"), sorted(EXPECTED))
def test_new_endpoint_permission(method: str, path: str) -> None:
    op = OPENAPI["paths"][path][method]
    assert op.get("x-permission") == EXPECTED[(method, path)]


def test_new_permissions_by_role() -> None:
    approve, quick = Permission.ATTACK_CATALOG_APPROVE, Permission.QUICK_TRY_USE
    assert {r for r in Role if approve in ROLE_PERMISSIONS[r]} == {Role.REVIEWER}
    assert {r for r in Role if quick in ROLE_PERMISSIONS[r]} == {Role.ENGINEER, Role.REVIEWER}
    # Đăng ký model vẫn dùng model.manage (admin) như hiện tại.
    assert {r for r in Role if Permission.MODEL_MANAGE in ROLE_PERMISSIONS[r]} == {Role.ADMIN}


def test_tool_worker_endpoints_use_worker_token() -> None:
    for path in (
        "/internal/worker/tool-lease",
        "/internal/worker/tool-jobs/{job_id}",
        "/internal/worker/tool-jobs/{job_id}/heartbeat",
        "/internal/worker/tool-jobs/{job_id}/result",
    ):
        for op in OPENAPI["paths"][path].values():
            assert "x-permission" not in op, path
            assert op.get("security"), path
