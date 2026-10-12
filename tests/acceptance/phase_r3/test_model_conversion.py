"""Đề xuất contract 003, Phase R3 — Chuyển `.pt` sang safetensors trong sandbox (marker `db`).

- `.pt` upload được nhưng `POST /models` vẫn từ chối (422); chỉ đi qua `POST /models/conversions`.
- Lượt chuyển là job `model_convert`; payload chỉ có presigned URL (API không mở file). Worker báo
  kết quả → `completed`, `metadata`, `result_upload_id`; file `.pt` gốc bị xóa khỏi MinIO; đăng ký
  được model từ `result_upload_id`.
- Mỗi người một lượt chưa xong (409); người khác xem lượt của mình → 404; reviewer → 403.
- Worker báo lỗi → `failed` kèm lỗi, file `.pt` gốc cũng bị xóa.

Sandbox thật được thay bằng safetensors dựng sẵn (sandbox có test riêng ở
`backend/worker/tests/test_converter.py`).
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import httpx
import pytest
import torch
from fastapi.testclient import TestClient
from safetensors.torch import save

from advertest_contracts.models import ModelConversionView, ModelSummary

from .conftest import ToolWorker, error, post, upload

pytestmark = pytest.mark.db

COCO = ["person", "bicycle", "car"]


def _safetensors() -> bytes:
    metadata = {
        "framework": "ultralytics",
        "architecture": "yolo11n",
        "names": '["person", "bicycle", "car"]',
        "imgsz": "640",
    }
    return save({"w": torch.rand(4)}, metadata=metadata)


def _convert(client: TestClient, upload_id: str, framework: str = "ultralytics") -> Any:
    return post(client, "/models/conversions", {"upload_id": upload_id, "framework": framework})


def _view(client: TestClient, conversion_id: str) -> ModelConversionView:
    response = client.get(f"/models/conversions/{conversion_id}")
    assert response.status_code == 200, response.text
    return ModelConversionView.model_validate(response.json())


def _lease(worker: ToolWorker) -> tuple[dict[str, Any], dict[str, Any]]:
    lease = worker.lease()
    assert lease is not None and lease["kind"] == "model_convert", lease
    return lease, worker.bundle(lease["job_id"])["payload"]


def test_convert_then_register(api: Any, tool_worker: ToolWorker) -> None:
    _, _, engineer = api.user("engineer")
    pt = b"\x80\x04" + uuid4().bytes  # nội dung không bao giờ được API mở
    upload_id = upload(engineer, "yolo11n.pt", pt)
    direct = post(
        engineer,
        "/models",
        {"name": f"pt-{uuid4().hex[:6]}", "framework": "ultralytics", "architecture": "yolo11n",
         "upload_id": upload_id, "class_names": COCO, "input_size": 640},
    )  # fmt: skip
    assert direct.status_code == 422, direct.text

    response = _convert(engineer, upload_id)
    assert response.status_code == 202, response.text
    conversion = ModelConversionView.model_validate(response.json())
    assert conversion.status == "queued" and conversion.metadata is None
    assert error(_convert(engineer, upload_id))[:2] == (409, "conflict")  # một lượt chưa xong
    _, _, other = api.user("engineer")
    assert other.get(f"/models/conversions/{conversion.id}").status_code == 404

    lease, payload = _lease(tool_worker)
    assert payload["conversion_id"] == str(conversion.id)
    assert payload["framework"] == "ultralytics"
    assert httpx.get(payload["source_url"], timeout=30).content == pt
    result = _safetensors()
    assert httpx.put(payload["result_upload_url"], content=result, timeout=30).status_code == 200
    report = {
        "kind": "model_convert",
        "metadata": {"framework": "ultralytics", "architecture": "yolo11n", "class_names": COCO,
                     "input_size": 640},
    }  # fmt: skip
    body = {"lease_id": lease["lease_id"], "report": report}
    assert tool_worker.result(lease["job_id"], body).status_code == 204

    done = _view(engineer, str(conversion.id))
    assert done.status == "completed" and done.result_upload_id is not None
    assert done.metadata is not None and done.metadata.class_names == COCO
    assert httpx.get(payload["source_url"], timeout=30).status_code == 404  # .pt đã bị xóa

    registered = post(
        engineer,
        "/models",
        {"name": f"pt-{uuid4().hex[:6]}", "framework": "ultralytics", "architecture": "yolo11n",
         "upload_id": str(done.result_upload_id), "class_names": COCO, "input_size": 640},
    )  # fmt: skip
    assert registered.status_code == 201, registered.text
    assert ModelSummary.model_validate(registered.json()).status == "checking"


def test_conversion_error_drops_source(api: Any, tool_worker: ToolWorker) -> None:
    _, _, engineer = api.user("engineer")
    upload_id = upload(engineer, "frcnn.pth", b"\x80\x04" + uuid4().bytes)
    response = _convert(engineer, upload_id, "torchvision")
    assert response.status_code == 202, response.text
    conversion_id = response.json()["id"]
    lease, payload = _lease(tool_worker)
    body = {"lease_id": lease["lease_id"], "error": "Không chuyển được file: UnpicklingError"}
    assert tool_worker.result(lease["job_id"], body).status_code == 204
    failed = _view(engineer, conversion_id)
    assert failed.status == "failed" and failed.error is not None and "Unpickling" in failed.error
    assert httpx.get(payload["source_url"], timeout=30).status_code == 404


def test_conversion_rejects_non_pickle_and_reviewer(api: Any) -> None:
    _, _, engineer = api.user("engineer")
    onnx = upload(engineer, "m.onnx", b"onnx" + uuid4().bytes)
    assert _convert(engineer, onnx).status_code == 422
    _, _, reviewer = api.user("reviewer")
    assert error(_convert(reviewer, onnx))[:2] == (403, "forbidden")
