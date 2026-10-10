"""Fixture cho test nghiệm thu Phase R2 (validation.md Phase R2, Automated Tests).

- Test không cần DB (Group 2, Group 3) chỉ dùng fixture trong `tests/fixtures/` (KITTI, YOLOv8n,
  `yolov8n.onnx`, `fcos_resnet50_fpn_coco.safetensors`).
- Test hệ thống (marker `db`, `make test-db`; Group 1, 4, 5) dùng lại hạ tầng của Phase 5: DB tạm
  đã migrate và seed, MinIO, API thật qua TestClient (đồng hồ giả), worker CPU thật `JobRunner`,
  slice KITTI 5 ảnh và YOLOv8n. DB được dựng sạch bằng `DROP OWNED BY` như Phase 7 (chạy chung
  phiên sau các phase khác).

Worker công cụ ở Group 4 được giả lập bằng chính API nội bộ (`/internal/worker/tool-*`, token của
compute target) để kiểm vòng đời mà không cần worker `--tools`; Group 5 chạy worker thật.

Interface mà test gọi trực tiếp ghi ở requirements.md Phase R2, mục "Chốt ở Group 0".
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, select, text
from sqlalchemy.orm import Session

from attacks.registry import get_spec, load_catalog
from backend.app.db import models as m
from backend.app.storage import (
    BUCKET_ARTIFACTS,
    BUCKET_DATASETS,
    BUCKET_MODELS,
    BUCKET_REPORTS,
    Buckets,
    make_s3_client,
)
from ml_core.fixtures import FIXTURES_DIR

from ._phase05 import load

P5 = load()

alembic_config = P5.alembic_config
app_engine = P5.app_engine
cli_env = P5.cli_env
world = P5.world
fresh_fingerprint = P5.fresh_fingerprint
post = P5.post
ok = P5.ok
error = P5.error
csrf = P5.csrf
DEV_OPEN = P5.DEV_OPEN

KITTI_IMAGE = FIXTURES_DIR / "kitti" / "image_2" / "000902.png"
ONNX_WEIGHTS = FIXTURES_DIR / "yolov8n.onnx"
TORCHVISION_WEIGHTS = FIXTURES_DIR / "fcos_resnet50_fpn_coco.safetensors"
YOLO_WEIGHTS = FIXTURES_DIR / "yolov8n.pt"


@pytest.fixture(scope="session")
def owner_engine(alembic_config: Config) -> Iterator[Engine]:
    """DB sạch bằng `DROP OWNED BY` rồi `upgrade head` (như Phase 7, Phase 8)."""
    engine = create_engine(P5.env("ADVERTEST_TEST_OWNER_URL"))
    with engine.begin() as conn:
        conn.execute(text("DROP OWNED BY advertest_owner"))
    command.upgrade(alembic_config, "head")
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def buckets(cli_env: dict[str, str]) -> Buckets:
    """Như Phase 8; xóa object của phase trước (DB vừa dựng lại)."""
    client = make_s3_client(
        cli_env["MINIO_ENDPOINT"], cli_env["MINIO_ACCESS_KEY"], cli_env["MINIO_SECRET_KEY"]
    )
    raw: Any = client
    existing = {b["Name"] for b in raw.list_buckets().get("Buckets", [])}
    for name in (BUCKET_MODELS, BUCKET_DATASETS, BUCKET_ARTIFACTS, BUCKET_REPORTS):
        if name not in existing:
            raw.create_bucket(Bucket=name)
            continue
        for page in raw.get_paginator("list_objects_v2").paginate(Bucket=name):
            keys = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
            if keys:
                raw.delete_objects(Bucket=name, Delete={"Objects": keys})
    return Buckets.from_client(client)


@pytest.fixture
def api(
    app_engine: Engine, buckets: Buckets, cli_env: dict[str, str], world: Any, tmp_path: Path
) -> Any:
    return P5.Api(app_engine, buckets, cli_env, world, tmp_path)


def unique(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def spec_of(name: str) -> Any:
    return get_spec(load_catalog(), name=name)


# ---------------------------------------------------------------- protocol


def required_grid(name: str, levels: list[float]) -> dict[str, Any]:
    return {
        "attack_spec_name": name,
        "spec_sha256": spec_of(name).spec_sha256,
        "mode": "grid",
        "grid": {"levels": levels},
    }


def max_drop(name: str, level: float, threshold: float = 0.9) -> dict[str, Any]:
    return {
        "kind": "max_drop_at_level",
        "attack_spec_name": name,
        "level": level,
        "threshold_kind": "relative_drop",
        "threshold": threshold,
        "class_filter": None,
    }


def protocol_body(**changes: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "description": "Kiểm thử nghiệm thu Phase R2.",
        "required_attacks": [required_grid("fgsm", [2.0, 4.0])],
        "min_slice_size": 5,
        "pass_criteria": [max_drop("fgsm", 4.0)],
        "cases_to_review_per_attack": 1,
        "forbid_dirty_runs": True,
    }
    body.update(changes)
    return body


def create_protocol(reviewer: TestClient, **changes: Any) -> dict[str, Any]:
    response = post(
        reviewer, "/protocols", {"name": unique("p_r2"), "body": protocol_body(**changes)}
    )
    created: dict[str, Any] = ok(response).json()
    return created


# ---------------------------------------------------------------- đọc DB


def audit_entries(engine: Engine, action: str, entity_id: UUID | str | None = None) -> list[Any]:
    with Session(engine) as session:
        query = select(m.AuditLog).where(m.AuditLog.action == action)
        if entity_id is not None:
            query = query.where(m.AuditLog.entity_id == UUID(str(entity_id)))
        return list(session.scalars(query).all())


def count_rows(engine: Engine, model: Any) -> int:
    with Session(engine) as session:
        return len(session.scalars(select(model)).all())


# ---------------------------------------------------------------- worker công cụ giả lập (Group 4)


@dataclass
class ToolWorker:
    """Gọi API nội bộ của job công cụ bằng token của compute target (như worker `--tools`)."""

    client: TestClient
    token: str
    target_id: str

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def lease(self) -> dict[str, Any] | None:
        response = self.client.post("/internal/worker/tool-lease", headers=self._headers())
        if response.status_code == 204:
            return None
        assert response.status_code == 200, response.text
        lease: dict[str, Any] = response.json()
        return lease

    def bundle(self, job_id: str) -> dict[str, Any]:
        response = self.client.get(f"/internal/worker/tool-jobs/{job_id}", headers=self._headers())
        assert response.status_code == 200, response.text
        bundle: dict[str, Any] = response.json()
        return bundle

    def heartbeat(self, job_id: str, lease_id: str) -> httpx.Response:
        return self.client.post(
            f"/internal/worker/tool-jobs/{job_id}/heartbeat",
            json={"lease_id": lease_id},
            headers=self._headers(),
        )

    def result(self, job_id: str, body: dict[str, Any]) -> httpx.Response:
        return self.client.post(
            f"/internal/worker/tool-jobs/{job_id}/result", json=body, headers=self._headers()
        )


@pytest.fixture
def tool_worker(api: Any) -> ToolWorker:
    """Worker công cụ giả lập; job còn sót của test trước (DB dùng chung cả phiên) được nhận và
    báo lỗi trước, để `lease()` trong test chỉ thấy job của chính test."""
    target = api.target()
    worker = ToolWorker(TestClient(api.app()), target.token, target.id)
    while (lease := worker.lease()) is not None:
        body = {"lease_id": lease["lease_id"], "error": "Dọn job của test trước"}
        assert worker.result(lease["job_id"], body).status_code == 204
    return worker


def spec_check_report(
    job_id_spec: str, worker_target_id: str, *, passed: bool, now: str
) -> dict[str, Any]:
    """Report `spec_check` đủ 7 mục; `passed = false` thì mục batch_invariant fail."""
    names = [
        "runs",
        "value_range",
        "pad_unchanged",
        "identity",
        "batch_invariant",
        "norm_bound",
        "deterministic",
    ]
    items = [
        {
            "name": name,
            "passed": passed or name != "batch_invariant",
            "details": None if passed or name != "batch_invariant" else "batch 1 và 4 lệch",
        }
        for name in names
    ]
    return {
        "kind": "spec_check",
        "result": {
            "spec_id": job_id_spec,
            "items": items,
            "passed": passed,
            "error": None,
            "checked_at": now,
            "worker_target_id": worker_target_id,
        },
    }


# ---------------------------------------------------------------- model qua web


def coco80() -> list[str]:
    import json

    import onnxruntime as ort

    session = ort.InferenceSession(str(ONNX_WEIGHTS), providers=["CPUExecutionProvider"])
    names: list[str] = json.loads(session.get_modelmeta().custom_metadata_map["class_names"])
    return names


def upload(admin: TestClient, filename: str, content: bytes) -> str:
    """`POST /models/uploads` rồi PUT nội dung lên presigned URL; trả `upload_id`."""
    response = post(admin, "/models/uploads", {"filename": filename, "size_bytes": len(content)})
    assert response.status_code == 200, response.text
    body = response.json()
    put = httpx.put(body["url"], content=content, timeout=120)
    assert put.status_code == 200, put.text
    upload_id: str = body["upload_id"]
    return upload_id


def register_onnx(
    admin: TestClient, content: bytes | None = None, **changes: Any
) -> httpx.Response:
    data = content if content is not None else ONNX_WEIGHTS.read_bytes()
    body = {
        "name": unique("onnx"),
        "framework": "onnx",
        "architecture": "yolov8n onnx (1, 84, 8400)",
        "upload_id": upload(admin, "model.onnx", data),
        "class_names": coco80(),
        "input_size": 640,
        **changes,
    }
    response: httpx.Response = post(admin, "/models", body)
    return response


def model_check_report(worker: ToolWorker, now: str, *, passed: bool) -> dict[str, Any]:
    return {
        "kind": "model_check",
        "result": {
            "passed": passed,
            "details": None if passed else "Không nạp được model",
            "gradient_check": None,
            "checked_at": now,
            "worker_target_id": worker.target_id,
        },
    }


def finish_model_check(worker: ToolWorker, api: Any, model_id: str, *, passed: bool) -> None:
    lease = worker.lease()
    assert lease is not None and lease["kind"] == "model_check", lease
    payload = worker.bundle(lease["job_id"])["payload"]
    assert payload["kind"] == "model_check"
    assert payload["model"]["model_version_id"] == model_id
    report = model_check_report(worker, api.clock().isoformat(), passed=passed)
    response = worker.result(lease["job_id"], {"lease_id": lease["lease_id"], "report": report})
    assert response.status_code == 204, response.text
