"""Đăng ký model qua web (requirements.md Phase R2, mục Model qua web; mission.md nguyên tắc 10).

- `POST /models/uploads`: presigned PUT vào `uploads/<upload_id>/<filename>` của bucket models.
  Schema đã chặn phần mở rộng khác `.onnx`/`.safetensors` và file quá 500 MB.
- `POST /models`: phần mở rộng phải khớp framework (torchvision ↔ safetensors, onnx ↔ onnx).
  Safetensors được kiểm header JSON ngay ở API (pickle, zip, rác → 422); onnx chỉ kiểm được ở
  worker (protobuf `ModelProto`). Weights chép sang `<sha>/weights.pt` (khóa chung cho mọi
  định dạng, nội dung opaque), model version ở `checking`, xếp job `model_check`.
- Kết quả pass: `ready`, ghi `card.json` để bundle của experiment dùng được; fail: `check_failed`.
  Web không bao giờ nhận pickle, nên không có đường nào nạp `.pt` từ upload.
"""

from __future__ import annotations

import hashlib
import json
import struct
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from advertest_contracts.enums import ModelStatus, ToolJobKind
from advertest_contracts.ids import content_id
from advertest_contracts.models import (
    MODEL_UPLOAD_MAX_BYTES,
    GradientCheck,
    ModelCard,
    ModelCheckPayload,
    ModelCheckResult,
    ModelRegister,
    ModelSummary,
    ModelUpload,
    ModelUploadCreate,
    ToolModel,
)
from backend.app import storage
from backend.app.db import models as m
from backend.app.presign import Presigner
from backend.app.services import audit, catalog, tool_jobs
from backend.app.services.errors import Conflict, Invalid, NotFound
from ml_core.models.register import lib_versions

EXTENSION = {"torchvision": ".safetensors", "onnx": ".onnx"}
# Header safetensors: 8 byte độ dài (little-endian) rồi JSON; giới hạn như thư viện safetensors.
SAFETENSORS_MAX_HEADER = 100 * 1024 * 1024
ONNX_NO_GRADIENT = "Model ONNX chỉ chạy inference, không hỗ trợ gradient"
NO_GRADIENT_RESULT = "Worker không gửi kết quả kiểm gradient"


def upload_prefix(upload_id: UUID) -> str:
    return f"uploads/{upload_id}/"


def create_upload(body: ModelUploadCreate, presigner: Presigner, now: datetime) -> ModelUpload:
    upload_id = uuid4()
    url = presigner.url(storage.BUCKET_MODELS, upload_prefix(upload_id) + body.filename, "PUT", now)
    return ModelUpload(upload_id=upload_id, url=url.url, expires_at=url.expires_at)


def is_safetensors(data: bytes) -> bool:
    """Header JSON hợp lệ: object, mỗi tensor có `dtype`, `shape`, `data_offsets` nằm trong file."""
    if len(data) < 8:
        return False
    (size,) = struct.unpack("<Q", data[:8])
    if size < 2 or size > SAFETENSORS_MAX_HEADER or 8 + size > len(data):
        return False
    try:
        header = json.loads(data[8 : 8 + size].decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return False
    if not isinstance(header, dict):
        return False
    body = len(data) - 8 - size
    tensors = {k: v for k, v in header.items() if k != "__metadata__"}
    if not tensors:
        return False
    for info in tensors.values():
        if not isinstance(info, dict) or not isinstance(info.get("dtype"), str):
            return False
        shape, offsets = info.get("shape"), info.get("data_offsets")
        if not isinstance(shape, list) or not all(isinstance(d, int) and d >= 0 for d in shape):
            return False
        if (
            not isinstance(offsets, list)
            or len(offsets) != 2
            or not all(isinstance(o, int) for o in offsets)
            or not 0 <= offsets[0] <= offsets[1] <= body
        ):
            return False
    return True


def _uploaded(buckets: storage.Buckets, upload_id: UUID) -> tuple[str, bytes]:
    keys = buckets.models.list(upload_prefix(upload_id))
    if len(keys) != 1:
        raise Invalid("upload_id chưa có file nào được upload")
    return keys[0], buckets.models.get(keys[0])


def register(
    session: Session,
    *,
    actor: m.User,
    body: ModelRegister,
    buckets: storage.Buckets,
    now: datetime,
) -> ModelSummary:
    key, data = _uploaded(buckets, body.upload_id)
    if not key.endswith(EXTENSION[body.framework]):
        raise Invalid(f"Model {body.framework} phải là file {EXTENSION[body.framework]}")
    if len(data) > MODEL_UPLOAD_MAX_BYTES:
        raise Invalid("File model vượt 500 MB")
    if body.framework == "torchvision" and not is_safetensors(data):
        raise Invalid("File không phải safetensors hợp lệ (pickle, zip, .pt không được nhận)")
    sha = hashlib.sha256(data).hexdigest()
    if session.scalar(select(m.ModelVersion.id).where(m.ModelVersion.weights_sha256 == sha)):
        raise Conflict("Đã có model cùng weights (trùng sha256)")
    buckets.models.put(storage.weights_key(sha), data)
    buckets.models.delete(key)

    model = session.scalar(select(m.Model).where(m.Model.name == body.name))
    if model is None:
        model = m.Model(name=body.name, created_by=actor.id)
        session.add(model)
        session.flush()
    version = m.ModelVersion(
        id=content_id(sha),
        model_id=model.id,
        weights_sha256=sha,
        weights_uri=f"s3://{storage.BUCKET_MODELS}/{storage.weights_key(sha)}",
        framework=body.framework,
        class_names=body.class_names,
        input_size=body.input_size,
        supports_gradients=False,
        status=ModelStatus.CHECKING,
        created_at=now,
    )
    session.add(version)
    session.flush()
    tool_jobs.enqueue(
        session,
        ToolJobKind.MODEL_CHECK,
        {"model_version_id": str(version.id), "architecture": body.architecture},
        created_by=actor.id,
        now=now,
    )
    audit.record(
        session,
        actor=actor,
        action="model.registered",
        entity_type="model_version",
        entity_id=version.id,
        after={"name": body.name, "framework": body.framework, "weights_sha256": sha},
    )
    return catalog.get_model(session, version.id)


def _version(session: Session, job: m.ToolJob) -> m.ModelVersion:
    version = session.get(
        m.ModelVersion, UUID(job.payload["model_version_id"]), with_for_update=True
    )
    if version is None:
        raise NotFound("Model của job không còn")
    return version


def tool_model(
    version: m.ModelVersion,
    architecture: str,
    presigner: Presigner,
    now: datetime,
) -> ToolModel:
    url = presigner.url(
        storage.BUCKET_MODELS, storage.weights_key(version.weights_sha256), "GET", now
    )
    return ToolModel.model_validate(
        {
            "model_version_id": version.id,
            "framework": version.framework,
            "architecture": architecture,
            "weights_sha256": version.weights_sha256,
            "class_names": version.class_names,
            "input_size": version.input_size,
            "weights_url": url.url,
        }
    )


def check_payload(
    session: Session, job: m.ToolJob, presigner: Presigner, now: datetime
) -> ModelCheckPayload:
    version = _version(session, job)
    return ModelCheckPayload(model=tool_model(version, job.payload["architecture"], presigner, now))


def _card(
    session: Session, version: m.ModelVersion, architecture: str, gradient: GradientCheck
) -> ModelCard:
    model = session.get(m.Model, version.model_id)
    assert model is not None  # khóa ngoại
    return ModelCard.model_validate(
        {
            "id": version.id,
            "name": model.name,
            "framework": version.framework,
            "architecture": architecture,
            "weights_sha256": version.weights_sha256,
            "class_names": version.class_names,
            "input_size": version.input_size,
            "supports_gradients": gradient.passed,
            "gradient_check": gradient,
            "lib_versions": lib_versions(),
        }
    )


def apply_check(
    session: Session, job: m.ToolJob, result: ModelCheckResult, buckets: storage.Buckets
) -> None:
    version = _version(session, job)
    if version.status != ModelStatus.CHECKING:
        raise Conflict(f"Model đang ở trạng thái {version.status}, không chờ kết quả kiểm tra")
    version.check = result.model_dump(mode="json")
    if not result.passed:
        version.status = ModelStatus.CHECK_FAILED
        session.flush()
        return
    gradient = result.gradient_check
    if version.framework == "onnx":
        gradient = GradientCheck(
            passed=False, checked_at=result.checked_at, details=ONNX_NO_GRADIENT
        )
    elif gradient is None:
        gradient = GradientCheck(
            passed=False, checked_at=result.checked_at, details=NO_GRADIENT_RESULT
        )
    card = _card(session, version, job.payload["architecture"], gradient)
    buckets.models.put(storage.card_key(version.weights_sha256), card.model_dump_json().encode())
    version.supports_gradients = card.supports_gradients
    version.status = ModelStatus.READY
    session.flush()


def check_error(session: Session, job: m.ToolJob, error: str, now: datetime) -> None:
    version = _version(session, job)
    if version.status != ModelStatus.CHECKING or job.leased_by is None:
        return
    result = ModelCheckResult(
        passed=False,
        details=error,
        gradient_check=None,
        checked_at=now,
        worker_target_id=job.leased_by,
    )
    version.check = result.model_dump(mode="json")
    version.status = ModelStatus.CHECK_FAILED
    session.flush()
