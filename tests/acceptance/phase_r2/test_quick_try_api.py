"""validation.md Phase R2, Group 4 — Thử nhanh qua API (`test_quick_try_api.py`, marker `db`).

- Lượt thứ hai khi lượt đầu chưa xong → 429 `quick_try_busy`; spec patch → 422; model ONNX gặp
  attack cần gradient → 422; ảnh sai định dạng, quá 10 MB hoặc cạnh dài quá 4096 px → 422.
- `not_a_test_result = true`; không tạo experiment, run, failure case; audit log `quick_try.create`.
- Chỉ người tạo xem được; kết quả worker (giả lập qua API nội bộ) hiện đủ level với nhãn từ
  metadata và ảnh qua `/artifacts/...`.
- Sau `expires_at` (đồng hồ giả): `GET` → 410 `gone`; dọn dẹp
  (`backend.app.services.quick_tries.purge_expired`) xóa object MinIO dưới `quick-tries/<id>/`.
"""

from __future__ import annotations

import io
from datetime import datetime
from typing import Any
from uuid import uuid4

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import Session

from advertest_contracts.models import QuickTryView
from backend.app.db import models as m
from backend.app.storage import BUCKET_ARTIFACTS, make_s3_client

from .conftest import (
    KITTI_IMAGE,
    ONNX_WEIGHTS,
    ToolWorker,
    audit_entries,
    count_rows,
    csrf,
    error,
    finish_model_check,
    register_onnx,
    spec_of,
)

pytestmark = pytest.mark.db

# Preset standard: 5 level (requirements.md Phase R2, Chốt ở Group 0, công thức level).
FGSM_STANDARD = [4.0, 8.0, 16.0, 24.0, 32.0]


def quick_try(
    client: TestClient,
    image: bytes,
    *,
    filename: str = "anh.png",
    content_type: str = "image/png",
    **fields: Any,
) -> httpx.Response:
    data = {k: str(v) for k, v in fields.items()}
    files = {"image": (filename, image, content_type)}
    response: httpx.Response = client.post(
        "/quick-tries", data=data, files=files, headers=csrf(client)
    )
    return response


def _png(width: int, height: int) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (120, 130, 140)).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def engineer(api: Any) -> TestClient:
    _, _, client = api.user("engineer")
    return client


def _fields(api: Any, spec: str = "fgsm", **changes: Any) -> dict[str, Any]:
    return {"model_version_id": api.world.model_id, "attack_spec_id": str(spec_of(spec).id),
            **changes}  # fmt: skip


def _keys(api: Any, prefix: str) -> list[str]:
    env = api.cli_env
    raw: Any = make_s3_client(
        env["MINIO_ENDPOINT"], env["MINIO_ACCESS_KEY"], env["MINIO_SECRET_KEY"]
    )
    response = raw.list_objects_v2(Bucket=BUCKET_ARTIFACTS, Prefix=prefix)
    return [obj["Key"] for obj in response.get("Contents", [])]


def _complete(worker: ToolWorker, quick_try_id: str) -> dict[str, Any]:
    """Giả lập worker: PUT ảnh (đã làm mờ) lên URL trong payload rồi gửi report."""
    lease = worker.lease()
    assert lease is not None and lease["kind"] == "quick_try", lease
    payload = worker.bundle(lease["job_id"])["payload"]
    assert payload["kind"] == "quick_try" and payload["quick_try_id"] == quick_try_id
    png = _png(640, 640)
    for url in [payload["clean_upload_url"], *payload["level_upload_urls"]]:
        assert httpx.put(url, content=png, timeout=60).status_code == 200
    objects = [
        {"bbox": [10, 10, 50, 90], "class_name": "person", "clean_score": 0.9,
         "attacked_score": 0.4, "status": "kept"},
        {"bbox": [100, 100, 200, 160], "class_name": "car", "clean_score": 0.8,
         "attacked_score": None, "status": "lost"},
    ]  # fmt: skip
    report = {"kind": "quick_try", "levels": [
        {"level": level, "objects": objects} for level in payload["levels"]
    ]}  # fmt: skip
    response = worker.result(lease["job_id"], {"lease_id": lease["lease_id"], "report": report})
    assert response.status_code == 204, response.text
    result: dict[str, Any] = payload
    return result


def test_quick_try_flow_and_expiry(api: Any, tool_worker: ToolWorker) -> None:
    _, email, engineer = api.user("engineer")
    counts = {
        model: count_rows(api.engine, model) for model in (m.Experiment, m.Run, m.FailureCase)
    }
    response = quick_try(engineer, KITTI_IMAGE.read_bytes(), **_fields(api))
    assert response.status_code == 202, response.text
    view = QuickTryView.model_validate(response.json())
    assert view.status == "queued" and view.not_a_test_result is True
    assert (view.expires_at - view.created_at).total_seconds() == 24 * 3600
    assert len(audit_entries(api.engine, "quick_try.create", view.id)) == 1

    busy = quick_try(engineer, KITTI_IMAGE.read_bytes(), **_fields(api, "fog"))
    assert error(busy)[:2] == (429, "quick_try_busy")

    _, _, other = api.user("engineer")
    assert other.get(f"/quick-tries/{view.id}").status_code == 404

    payload = _complete(tool_worker, str(view.id))
    assert payload["levels"] == FGSM_STANDARD
    done = QuickTryView.model_validate(engineer.get(f"/quick-tries/{view.id}").json())
    assert done.status == "completed" and done.not_a_test_result is True
    assert [lv.level for lv in done.levels] == FGSM_STANDARD
    assert done.clean_image_url is not None
    for url in [done.clean_image_url, *(lv.image_url for lv in done.levels)]:
        image = engineer.get(url)
        assert image.status_code == 200, url
        assert image.headers["content-type"].startswith("image/")
    assert {model: count_rows(api.engine, model) for model in counts} == counts

    # Lượt mới được phép sau khi lượt trước xong.
    second = quick_try(engineer, KITTI_IMAGE.read_bytes(), **_fields(api, "fog"))
    assert second.status_code == 202, second.text

    prefix = f"quick-tries/{view.id}/"
    assert _keys(api, prefix)
    api.clock.advance(24 * 3600 + 1)
    # Phiên cũ cũng hết hạn sau 24 giờ đồng hồ giả: đăng nhập lại bằng client mới.
    engineer = api.client()
    api.login(engineer, email)
    assert error(engineer.get(f"/quick-tries/{view.id}"))[:2] == (410, "gone")
    now: datetime = api.clock()
    from backend.app.services.quick_tries import purge_expired  # Group 4

    with Session(api.engine) as session, session.begin():
        assert purge_expired(session, api.buckets, now) >= 1
    assert _keys(api, prefix) == []
    assert engineer.get(done.clean_image_url).status_code in (404, 410)
    assert error(engineer.get(f"/quick-tries/{view.id}"))[:2] == (410, "gone")


def test_level_labels_from_metadata(api: Any, tool_worker: ToolWorker) -> None:
    _, _, admin = api.user("admin")
    fog = spec_of("fog")
    meta = {"display_name": "Sương mù", "description": "Sương mù.", "realism": "high",
            "level_labels": {"1": "rất nhẹ", "3": "vừa"}}  # fmt: skip
    patched = admin.patch(f"/admin/attack-specs/{fog.id}/metadata", json=meta, headers=csrf(admin))
    assert patched.status_code == 200, patched.text
    _, _, engineer = api.user("engineer")
    response = quick_try(engineer, KITTI_IMAGE.read_bytes(), **_fields(api, "fog"))
    assert response.status_code == 202, response.text
    quick_try_id = response.json()["id"]
    _complete(tool_worker, quick_try_id)
    done = QuickTryView.model_validate(engineer.get(f"/quick-tries/{quick_try_id}").json())
    labels = {lv.level: lv.label for lv in done.levels}
    assert labels[1.0] == "rất nhẹ" and labels[3.0] == "vừa"
    assert labels[2.0] is None


def test_rejects_patch_and_bad_images(api: Any, engineer: TestClient) -> None:
    patch = quick_try(engineer, KITTI_IMAGE.read_bytes(), **_fields(api, "adv_patch"))
    assert error(patch)[0] == 422
    text = quick_try(engineer, b"khong phai anh", filename="a.png")
    assert error(text)[0] == 422
    wide = quick_try(engineer, _png(4097, 8), **_fields(api))
    assert error(wide)[0] == 422
    noise = np.random.default_rng(0).integers(0, 255, (2000, 2000, 3), dtype=np.uint8)
    buffer = io.BytesIO()
    Image.fromarray(noise).save(buffer, format="PNG")  # PNG nhiễu không nén được: > 10 MB
    big = buffer.getvalue()
    assert len(big) > 10 * 1024 * 1024
    assert error(quick_try(engineer, big, **_fields(api)))[0] == 422


def test_onnx_model_with_gradient_attack_rejected(
    api: Any, engineer: TestClient, tool_worker: ToolWorker
) -> None:
    _, _, admin = api.user("admin")
    # Nội dung riêng (sha mới) để không trùng model ONNX của test khác; kiểm tra do worker giả lập.
    response = register_onnx(admin, content=ONNX_WEIGHTS.read_bytes() + uuid4().bytes)
    assert response.status_code == 201, response.text
    model_id = response.json()["id"]
    finish_model_check(tool_worker, api, model_id, passed=True)
    fgsm = quick_try(engineer, KITTI_IMAGE.read_bytes(), **_fields(api, model_version_id=model_id))
    assert error(fgsm)[0] == 422
    fog = quick_try(
        engineer, KITTI_IMAGE.read_bytes(), **_fields(api, "fog", model_version_id=model_id)
    )
    assert fog.status_code == 202, fog.text


def test_permissions(api: Any) -> None:
    _, _, admin = api.user("admin")
    assert error(quick_try(admin, KITTI_IMAGE.read_bytes(), **_fields(api)))[:2] == (
        403, "forbidden",
    )  # fmt: skip
    _, _, reviewer = api.user("reviewer")
    assert quick_try(reviewer, KITTI_IMAGE.read_bytes(), **_fields(api)).status_code == 202
