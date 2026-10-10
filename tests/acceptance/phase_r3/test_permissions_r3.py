"""validation.md Phase R3, Group 1 — Endpoint mới có `x-permission` đúng (bổ sung ma trận quyền
Phase 4 và R2). Không cần DB; đọc `contracts/openapi.json`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

OPENAPI: dict[str, Any] = json.loads(
    (Path(__file__).resolve().parents[3] / "contracts" / "openapi.json").read_text()
)


def test_recheck_model_permission() -> None:
    op = OPENAPI["paths"]["/models/{model_id}/check"]["post"]
    assert op.get("x-permission") == "model.manage"
    assert "202" in op["responses"] and "409" in op["responses"]
