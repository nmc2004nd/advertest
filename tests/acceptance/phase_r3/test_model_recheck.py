"""validation.md Phase R3, Group 1 — Kiểm lại model (`test_model_recheck.py`, marker `db`).

- `POST /models/{id}/check` từ `check_failed` → 202, `checking`, có job `model_check` mới, audit
  `model.rechecked`; job pass thì model `ready`.
- Từ `ready` hoặc `checking` → 409; weights đã xóa khỏi storage → 409.
- Engineer, reviewer gọi → 403 (`model.manage` chỉ dành cho admin).

Job `model_check` giả lập qua API nội bộ của worker (như R2 `test_model_upload.py`).
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from advertest_contracts.models import ModelSummary
from backend.app.storage import weights_key

from .conftest import (
    ONNX_WEIGHTS,
    ToolWorker,
    audit_entries,
    error,
    finish_model_check,
    post,
    register_onnx,
)

pytestmark = pytest.mark.db


@pytest.fixture
def admin(api: Any) -> TestClient:
    _, _, client = api.user("admin")
    admin: TestClient = client
    return admin


def _model(client: TestClient, model_id: str) -> ModelSummary:
    response = client.get(f"/models/{model_id}")
    assert response.status_code == 200, response.text
    return ModelSummary.model_validate(response.json())


def _registered(admin: TestClient) -> ModelSummary:
    """Model ONNX mới (sha riêng cho từng test), đang `checking`."""
    response = register_onnx(admin, content=ONNX_WEIGHTS.read_bytes() + uuid4().bytes)
    assert response.status_code == 201, response.text
    return ModelSummary.model_validate(response.json())


def _failed(api: Any, admin: TestClient, worker: ToolWorker) -> ModelSummary:
    model = _registered(admin)
    finish_model_check(worker, api, str(model.id), passed=False)
    assert _model(admin, str(model.id)).status == "check_failed"
    return model


def _recheck(client: TestClient, model_id: str) -> Any:
    return post(client, f"/models/{model_id}/check")


def test_recheck_failed_model(api: Any, admin: TestClient, tool_worker: ToolWorker) -> None:
    model = _failed(api, admin, tool_worker)
    response = _recheck(admin, str(model.id))
    assert response.status_code == 202, response.text
    view = ModelSummary.model_validate(response.json())
    assert view.id == model.id and view.status == "checking"
    assert _model(admin, str(model.id)).status == "checking"
    assert len(audit_entries(api.engine, "model.rechecked", model.id)) == 1

    # Có job model_check mới cho đúng model; pass thì model sẵn sàng.
    finish_model_check(tool_worker, api, str(model.id), passed=True)
    ready = _model(admin, str(model.id))
    assert ready.status == "ready" and ready.check is not None and ready.check.passed


def test_recheck_rejects_other_status(api: Any, admin: TestClient, tool_worker: ToolWorker) -> None:
    model = _registered(admin)
    assert error(_recheck(admin, str(model.id)))[:2] == (409, "conflict")  # checking
    finish_model_check(tool_worker, api, str(model.id), passed=True)
    assert error(_recheck(admin, str(model.id)))[:2] == (409, "conflict")  # ready
    assert audit_entries(api.engine, "model.rechecked", model.id) == []
    assert tool_worker.lease() is None  # không xếp job nào


def test_recheck_missing_weights(api: Any, admin: TestClient, tool_worker: ToolWorker) -> None:
    model = _failed(api, admin, tool_worker)
    api.buckets.models.delete(weights_key(model.weights_sha256))
    status, _, _ = error(_recheck(admin, str(model.id)))
    assert status == 409
    assert _model(admin, str(model.id)).status == "check_failed"
    assert tool_worker.lease() is None


@pytest.mark.parametrize("role", ["engineer", "reviewer"])
def test_recheck_requires_model_manage(
    api: Any, admin: TestClient, tool_worker: ToolWorker, role: str
) -> None:
    model = _failed(api, admin, tool_worker)
    _, _, client = api.user(role)
    assert error(_recheck(client, str(model.id)))[:2] == (403, "forbidden")
