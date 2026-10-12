"""Đổi `.pt`/`.pth` upload qua web sang `.safetensors` trong sandbox (Phase R3, đề xuất contract
003; mission.md nguyên tắc 10).

- `POST /models/conversions`: file đã upload qua `POST /models/uploads` (`.pt`/`.pth`) → job công
  cụ `model_convert`. Mỗi người chỉ một lượt chưa xong (409). API không bao giờ đọc nội dung file.
- Worker công cụ tải file, chuyển byte sang sandbox chuyển đổi, PUT `.safetensors` kết quả lên
  `uploads/<result_upload_id>/` rồi báo metadata. Người dùng đăng ký bằng `result_upload_id` như
  file safetensors tự upload; model vẫn qua `model_check`.
- Xong (thành công hay lỗi) thì xóa file `.pt` gốc khỏi MinIO.
- Trạng thái và kết quả nằm trong `tool_jobs`; `id` của lượt chuyển là id của job. Chỉ người tạo
  xem được lượt của mình (người khác: 404).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import PurePosixPath
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from advertest_contracts.enums import ToolJobKind, ToolJobStatus
from advertest_contracts.models import (
    ModelConversionCreate,
    ModelConversionView,
    ModelConvertMetadata,
    ModelConvertPayload,
    ModelConvertReport,
)
from backend.app import storage
from backend.app.db import models as m
from backend.app.presign import Presigner
from backend.app.services import audit, tool_jobs
from backend.app.services.errors import Conflict, Invalid, NotFound
from backend.app.services.model_uploads import upload_prefix

PICKLE_EXTENSIONS = (".pt", ".pth")


def _source_key(buckets: storage.Buckets, upload_id: UUID) -> str:
    keys = buckets.models.list(upload_prefix(upload_id))
    if len(keys) != 1:
        raise Invalid("upload_id chưa có file nào được upload")
    if not keys[0].endswith(PICKLE_EXTENSIONS):
        raise Invalid(
            "Chỉ chuyển đổi file .pt hoặc .pth; file .onnx/.safetensors đăng ký trực tiếp"
        )
    return keys[0]


def view(job: m.ToolJob) -> ModelConversionView:
    done = job.status == ToolJobStatus.COMPLETED
    report = ModelConvertReport.model_validate(job.result) if done and job.result else None
    return ModelConversionView(
        id=job.id,
        status=job.status,
        framework=job.payload["framework"],
        result_upload_id=UUID(job.payload["result_upload_id"]) if report else None,
        metadata=report.metadata if report else None,
        error=job.error if job.status == ToolJobStatus.FAILED else None,
        created_at=job.created_at,
    )


def create(
    session: Session,
    *,
    actor: m.User,
    body: ModelConversionCreate,
    buckets: storage.Buckets,
    now: datetime,
) -> ModelConversionView:
    busy = session.scalar(
        select(m.ToolJob.id).where(
            m.ToolJob.kind == ToolJobKind.MODEL_CONVERT,
            m.ToolJob.created_by == actor.id,
            m.ToolJob.status.in_([ToolJobStatus.QUEUED, ToolJobStatus.RUNNING]),
        )
    )
    if busy is not None:
        raise Conflict("Bạn đang có một lượt chuyển đổi chưa xong; chờ lượt đó kết thúc")
    key = _source_key(buckets, body.upload_id)
    job = tool_jobs.enqueue(
        session,
        ToolJobKind.MODEL_CONVERT,
        {
            "framework": body.framework,
            "source_key": key,
            "result_upload_id": str(uuid4()),
            "result_name": f"{PurePosixPath(key).stem}.safetensors",
        },
        created_by=actor.id,
        now=now,
    )
    audit.record(
        session,
        actor=actor,
        action="model.conversion_requested",
        entity_type="tool_job",
        entity_id=job.id,
        after={"framework": body.framework, "source_key": key},
    )
    return view(job)


def get(session: Session, *, actor: m.User, conversion_id: UUID) -> ModelConversionView:
    job = session.get(m.ToolJob, conversion_id)
    if job is None or job.kind != ToolJobKind.MODEL_CONVERT or job.created_by != actor.id:
        raise NotFound("Không có lượt chuyển đổi này")
    return view(job)


def _result_key(job: m.ToolJob) -> str:
    name: str = job.payload["result_name"]
    return upload_prefix(UUID(job.payload["result_upload_id"])) + name


def payload(job: m.ToolJob, presigner: Presigner, now: datetime) -> ModelConvertPayload:
    bucket = storage.BUCKET_MODELS
    return ModelConvertPayload(
        conversion_id=job.id,
        framework=job.payload["framework"],
        source_url=presigner.url(bucket, job.payload["source_key"], "GET", now).url,
        result_upload_url=presigner.url(bucket, _result_key(job), "PUT", now).url,
    )


def _drop_source(job: m.ToolJob, buckets: storage.Buckets) -> None:
    key = job.payload["source_key"]
    if buckets.models.exists(key):
        buckets.models.delete(key)


def apply_result(job: m.ToolJob, metadata: ModelConvertMetadata, buckets: storage.Buckets) -> None:
    """Kết quả phải đã được PUT; framework của metadata phải khớp yêu cầu."""
    if not buckets.models.exists(_result_key(job)):
        raise Invalid("Chưa upload file .safetensors kết quả")
    if metadata.framework != job.payload["framework"]:
        raise Invalid(f"metadata.framework phải là {job.payload['framework']}")
    _drop_source(job, buckets)


def on_error(job: m.ToolJob, buckets: storage.Buckets) -> None:
    _drop_source(job, buckets)
