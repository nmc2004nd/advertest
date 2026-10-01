"""validation.md Phase 6, Quyền: catalog đầy đủ cho `/admin/attacks` chỉ admin đọc được."""

from __future__ import annotations

from typing import Any

import pytest

from .conftest import World6

pytestmark = pytest.mark.db


def test_full_catalog_admin_only(api: Any, world: World6) -> None:
    admin = api.admin()
    response = admin.get("/admin/attack-specs?limit=100")
    assert response.status_code == 200, response.text
    names = {item["name"] for item in response.json()["items"]}
    assert {"fgsm", "fog", "bbox_occlusion", "adv_patch"} <= names
    for role in ("engineer", "reviewer"):
        _, _, client = api.user(role)
        denied = client.get("/admin/attack-specs")
        assert denied.status_code == 403, role
