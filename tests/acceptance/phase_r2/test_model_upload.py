"""validation.md Phase R2, Group 4 — Model qua web (`test_model_upload.py`, marker `db`).

- Upload `.pkl`, zip, hoặc file không phải safetensors/onnx/pt → 422 (mission.md nguyên tắc 10). Từ
  Phase R3 (đề xuất contract 003) `.pt`/`.pth` upload được để chuyển đổi trong sandbox, còn
  `POST /models` vẫn từ chối (`tests/acceptance/phase_r3/test_model_conversion.py`).
- `POST /models` tạo model `checking`, id = content_id(weights_sha256); trùng sha → 409; xếp job
  `model_check`; kết quả pass → `ready`, fail → `check_failed`.
- Model `checking`/`check_failed` không dùng được trong experiment; engineer và admin đăng ký được,
  engineer không thêm version vào model trùng tên của người khác (409).

Job `model_check` được giả lập qua API nội bộ của worker; worker thật ở `test_tool_worker.py`.
"""

from __future__ import annotations

import hashlib
import io
import pickle
import zipfile
from typing import Any
from uuid import uuid4

import pytest

from advertest_contracts.ids import content_id
from advertest_contracts.models import ModelSummary

from .conftest import (
    ONNX_WEIGHTS,
    P5,
    ToolWorker,
    audit_entries,
    error,
    finish_model_check,
    post,
    register_onnx,
    upload,
)

pytestmark = pytest.mark.db


@pytest.fixture
def admin(api: Any) -> Any:
    _, _, client = api.user("admin")
    return client


def _model(client: Any, model_id: str) -> ModelSummary:
    response = client.get(f"/models/{model_id}")
    assert response.status_code == 200, response.text
    return ModelSummary.model_validate(response.json())


@pytest.mark.parametrize(
    "filename", ["model.pkl", "model.zip", "model.ckpt", "model.pt.zip", "model"]
)
def test_upload_rejects_other_extensions(admin: Any, filename: str) -> None:
    response = post(admin, "/models/uploads", {"filename": filename, "size_bytes": 1024})
    assert response.status_code == 422, response.text


def test_upload_size_limit(admin: Any) -> None:
    too_big = {"filename": "model.onnx", "size_bytes": 500 * 1024 * 1024 + 1}
    assert post(admin, "/models/uploads", too_big).status_code == 422


def test_reviewer_cannot_upload(api: Any) -> None:
    _, _, reviewer = api.user("reviewer")
    body = {"filename": "model.onnx", "size_bytes": 1024}
    assert error(post(reviewer, "/models/uploads", body))[:2] == (403, "forbidden")


def test_engineer_registers_own_model(api: Any, admin: Any) -> None:
    _, _, engineer = api.user("engineer")
    response = register_onnx(engineer, content=ONNX_WEIGHTS.read_bytes() + uuid4().bytes)
    assert response.status_code == 201, response.text
    name = ModelSummary.model_validate(response.json()).name

    # Cùng tên: chủ model thêm version được, engineer khác thì 409; admin không bị giới hạn.
    again = register_onnx(engineer, content=ONNX_WEIGHTS.read_bytes() + uuid4().bytes, name=name)
    assert again.status_code == 201, again.text
    _, _, other = api.user("engineer")
    taken = register_onnx(other, content=ONNX_WEIGHTS.read_bytes() + uuid4().bytes, name=name)
    assert error(taken)[:2] == (409, "conflict")
    by_admin = register_onnx(admin, content=ONNX_WEIGHTS.read_bytes() + uuid4().bytes, name=name)
    assert by_admin.status_code == 201, by_admin.text


def _pickle_bytes() -> bytes:
    return pickle.dumps({"weights": [1, 2, 3]})


def _zip_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("archive/data.pkl", _pickle_bytes())
    return buffer.getvalue()


@pytest.mark.parametrize("content", [_pickle_bytes(), _zip_bytes(), b"khong phai safetensors"])
def test_register_rejects_non_safetensors_content(admin: Any, content: bytes) -> None:
    body = {
        "name": "fcos-gia",
        "framework": "torchvision",
        "architecture": "fcos_resnet50_fpn",
        "upload_id": upload(admin, "model.safetensors", content),
        "class_names": ["person", "car"],
        "input_size": 640,
    }
    status, _, _ = error(post(admin, "/models", body))
    assert status == 422


@pytest.mark.parametrize(
    ("filename", "content"),
    [("yolov8n.safetensors", _pickle_bytes()), ("yolov8n.onnx", ONNX_WEIGHTS.read_bytes())],
)
def test_register_ultralytics_needs_safetensors(admin: Any, filename: str, content: bytes) -> None:
    body = {
        "name": "yolov8n-gia",
        "framework": "ultralytics",
        "architecture": "yolov8n",
        "upload_id": upload(admin, filename, content),
        "class_names": ["person", "car"],
        "input_size": 640,
    }
    status, _, _ = error(post(admin, "/models", body))
    assert status == 422


def test_register_onnx_lifecycle(api: Any, admin: Any, tool_worker: ToolWorker) -> None:
    # Nội dung riêng (sha mới): model ONNX thật được đăng ký ở test worker công cụ (Group 5).
    content = ONNX_WEIGHTS.read_bytes() + uuid4().bytes
    response = register_onnx(admin, content=content)
    assert response.status_code == 201, response.text
    model = ModelSummary.model_validate(response.json())
    sha = hashlib.sha256(content).hexdigest()
    assert model.weights_sha256 == sha
    assert str(model.id) == str(content_id(sha))
    assert model.status == "checking" and model.supports_gradients is False
    assert model.framework == "onnx"
    assert len(audit_entries(api.engine, "model.registered", model.id)) == 1

    assert error(register_onnx(admin, content=content))[:2] == (409, "conflict")  # trùng sha

    _, _, engineer = api.user("engineer")
    target = api.target()
    body = api.body(target, [P5.attack("fog", [1.0])], model_version_id=str(model.id))
    status, _, paths = error(post(engineer, "/experiments", body))
    assert status == 422 and "model_version_id" in paths

    finish_model_check(tool_worker, api, str(model.id), passed=True)
    ready = _model(engineer, str(model.id))
    assert ready.status == "ready" and ready.check is not None and ready.check.passed
    assert str(model.id) in {m["id"] for m in engineer.get("/models").json()}


def test_check_failed_model_is_unusable(api: Any, admin: Any, tool_worker: ToolWorker) -> None:
    response = register_onnx(admin, content=b"khong phai onnx " + bytes(range(64)))
    assert response.status_code == 201, response.text  # onnx chỉ kiểm nội dung ở worker
    model_id = response.json()["id"]
    finish_model_check(tool_worker, api, model_id, passed=False)
    failed = _model(admin, model_id)
    assert failed.status == "check_failed"
    assert failed.check is not None and failed.check.details

    _, _, engineer = api.user("engineer")
    target = api.target()
    body = api.body(target, [P5.attack("fog", [1.0])], model_version_id=model_id)
    status, _, paths = error(post(engineer, "/experiments", body))
    assert status == 422 and "model_version_id" in paths
