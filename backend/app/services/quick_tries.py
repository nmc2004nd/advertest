"""Thử nhanh một ảnh (requirements.md Phase R2, mục Thử nhanh).

- Ảnh JPEG/PNG ≤ 10 MB, cạnh dài ≤ 4096 px; model `ready`, spec `active`; spec cần train (patch)
  hoặc model không có gradient gặp attack cần gradient → 422. Mỗi người tối đa 1 lượt
  `queued`/`running` (429 `quick_try_busy`).
- Level theo preset (công thức của bản nháp experiment). Worker tính mọi level trong một job
  `quick_try`, PUT ảnh sạch và ảnh bị tấn công đã làm mờ lên presigned URL, rồi gửi bảng object.
- Không tạo experiment, run hay failure case; kết quả giữ 24 giờ. `GET` chỉ cho người tạo
  (người khác: 404), hết hạn: 410. `purge_expired` xóa mọi object dưới `quick-tries/<id>/` và
  đặt `deleted_at`. Ảnh gốc (chưa làm mờ) chỉ có presigned GET cho worker, không bao giờ được cấp
  URL `/artifacts/...` (`artifacts.verify` từ chối khóa `original`).
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import logging
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from advertest_contracts.enums import (
    AttackSpecStatus,
    ModelStatus,
    ToolJobKind,
    ToolJobStatus,
)
from advertest_contracts.models import (
    ModelCard,
    PresetKey,
    QuickTryLevel,
    QuickTryPayload,
    QuickTryReport,
    QuickTryView,
)
from backend.app import storage
from backend.app.db import models as m
from backend.app.presign import Method, Presigner
from backend.app.services import artifacts, attack_catalog, audit, drafts, model_uploads, tool_jobs
from backend.app.services.clock import Clock, utcnow
from backend.app.services.errors import Gone, Invalid, NotFound, QuickTryBusy

logger = logging.getLogger(__name__)

RETENTION = timedelta(hours=24)
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_SIDE = 4096
FORMATS = {"PNG": "png", "JPEG": "jpg"}
EXPIRED_ERROR = "Lượt thử nhanh hết hạn trước khi worker chạy xong"
PURGE_INTERVAL_S = 600.0


# ---------------------------------------------------------------- khóa MinIO (bucket artifacts)


def prefix(quick_try_id: UUID) -> str:
    return f"quick-tries/{quick_try_id}/"


def original_key(quick_try_id: UUID, extension: str) -> str:
    return f"{prefix(quick_try_id)}{artifacts.QUICK_TRY_ORIGINAL}.{extension}"


def clean_key(quick_try_id: UUID) -> str:
    return f"{prefix(quick_try_id)}clean.png"


def level_key(quick_try_id: UUID, index: int) -> str:
    return f"{prefix(quick_try_id)}level-{index}.png"


# ---------------------------------------------------------------- tạo


def image_extension(data: bytes) -> str:
    """Phần mở rộng lưu ảnh gốc; ảnh sai định dạng, quá lớn hoặc hỏng → `Invalid`."""
    if len(data) > MAX_IMAGE_BYTES:
        raise Invalid("Ảnh vượt 10 MB")
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in FORMATS:
                raise Invalid("Chỉ nhận ảnh JPEG hoặc PNG")
            if max(image.size) > MAX_IMAGE_SIDE:
                raise Invalid(f"Cạnh dài của ảnh vượt {MAX_IMAGE_SIDE} px")
            image.load()
            return FORMATS[image.format]
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise Invalid("Không đọc được ảnh (chỉ nhận JPEG hoặc PNG)") from exc


def _levels(spec_row: m.AttackSpecRow, preset: PresetKey) -> list[float]:
    chosen = next(p for p in drafts.experiment_presets() if p.key == preset)
    return drafts.levels_at(attack_catalog.spec_of(spec_row).primary_param, chosen.level_ratios)


def create(
    session: Session,
    *,
    actor: m.User,
    model_version_id: UUID,
    attack_spec_id: UUID,
    preset: PresetKey,
    image: bytes,
    buckets: storage.Buckets,
    now: datetime,
) -> QuickTryView:
    version = session.get(m.ModelVersion, model_version_id)
    if version is None or version.status != ModelStatus.READY:
        raise Invalid("Model không có hoặc chưa sẵn sàng")
    spec_row = session.get(m.AttackSpecRow, attack_spec_id)
    if spec_row is None or spec_row.status != AttackSpecStatus.ACTIVE:
        raise Invalid("Attack spec không có hoặc không hoạt động")
    spec = attack_catalog.spec_of(spec_row)
    if spec.requires_training:
        raise Invalid("Thử nhanh không hỗ trợ attack cần train (patch)")
    if spec.requires_gradients and not version.supports_gradients:
        raise Invalid(f"{spec.name} cần gradient, model này không hỗ trợ")
    extension = image_extension(image)
    levels = _levels(spec_row, preset)

    # Khóa dòng user: hai request cùng lúc của một người không cùng lọt qua giới hạn 1 lượt.
    session.get(m.User, actor.id, with_for_update=True)
    busy = session.scalar(
        select(m.QuickTry.id)
        .join(m.ToolJob, m.ToolJob.id == m.QuickTry.tool_job_id)
        .where(
            m.QuickTry.owner_id == actor.id,
            m.ToolJob.status.in_((ToolJobStatus.QUEUED, ToolJobStatus.RUNNING)),
        )
        .limit(1)
    )
    if busy is not None:
        raise QuickTryBusy("Đang có một lượt thử nhanh chưa xong")

    quick_try_id = uuid4()
    key = original_key(quick_try_id, extension)
    buckets.artifacts.put(key, image)
    job = tool_jobs.enqueue(
        session,
        ToolJobKind.QUICK_TRY,
        {"quick_try_id": str(quick_try_id), "levels": levels},
        created_by=actor.id,
        now=now,
    )
    row = m.QuickTry(
        id=quick_try_id,
        owner_id=actor.id,
        tool_job_id=job.id,
        model_version_id=version.id,
        attack_spec_id=spec_row.id,
        preset=preset,
        input_uri=f"s3://{storage.BUCKET_ARTIFACTS}/{key}",
        created_at=now,
        expires_at=now + RETENTION,
    )
    session.add(row)
    session.flush()
    audit.record(
        session,
        actor=actor,
        action="quick_try.create",
        entity_type="quick_try",
        entity_id=row.id,
        after={
            "model_version_id": str(version.id),
            "attack_spec_id": str(spec_row.id),
            "preset": preset,
        },
    )
    return _view(session, row, job, now)


# ---------------------------------------------------------------- đọc


def _view(session: Session, row: m.QuickTry, job: m.ToolJob, now: datetime) -> QuickTryView:
    completed = job.status == ToolJobStatus.COMPLETED
    levels: list[QuickTryLevel] = []
    clean_url = None
    if completed:
        assert job.result is not None  # completed ⇒ có report
        report = QuickTryReport.model_validate(job.result)
        spec_row = session.get(m.AttackSpecRow, row.attack_spec_id)
        metadata = attack_catalog.metadata_of(spec_row) if spec_row is not None else None
        clean_url = f"/artifacts/{artifacts.issue(clean_key(row.id), now)[0]}"
        levels = [
            QuickTryLevel(
                level=level.level,
                label=metadata.label_for(level.level) if metadata is not None else None,
                image_url=f"/artifacts/{artifacts.issue(level_key(row.id, i), now)[0]}",
                objects=level.objects,
            )
            for i, level in enumerate(report.levels)
        ]
    return QuickTryView.model_validate(
        {
            "id": row.id,
            "status": job.status,
            "model_version_id": row.model_version_id,
            "attack_spec_id": row.attack_spec_id,
            "preset": row.preset,
            "clean_image_url": clean_url,
            "levels": levels,
            "created_at": row.created_at,
            "expires_at": row.expires_at,
            "error": job.error if job.status == ToolJobStatus.FAILED else None,
        }
    )


def get(session: Session, *, actor_id: UUID, quick_try_id: UUID, now: datetime) -> QuickTryView:
    row = session.get(m.QuickTry, quick_try_id)
    if row is None or row.owner_id != actor_id:
        raise NotFound("Không có lượt thử nhanh này")
    if row.deleted_at is not None or now >= row.expires_at:
        raise Gone("Lượt thử nhanh đã hết hạn")
    job = session.get(m.ToolJob, row.tool_job_id)
    assert job is not None  # khóa ngoại
    return _view(session, row, job, now)


# ---------------------------------------------------------------- job của worker


def _row(session: Session, job: m.ToolJob) -> m.QuickTry:
    row = session.get(m.QuickTry, UUID(job.payload["quick_try_id"]))
    if row is None:
        raise NotFound("Lượt thử nhanh của job không còn")
    return row


def payload(
    session: Session,
    job: m.ToolJob,
    buckets: storage.Buckets,
    presigner: Presigner,
    now: datetime,
) -> QuickTryPayload:
    row = _row(session, job)
    version = session.get(m.ModelVersion, row.model_version_id)
    spec_row = session.get(m.AttackSpecRow, row.attack_spec_id)
    assert version is not None and spec_row is not None  # khóa ngoại
    card = ModelCard.model_validate_json(
        buckets.models.get(storage.card_key(version.weights_sha256))
    )
    levels: list[float] = job.payload["levels"]
    original = row.input_uri.removeprefix(f"s3://{storage.BUCKET_ARTIFACTS}/")

    def url(key: str, method: Method) -> str:
        return presigner.url(storage.BUCKET_ARTIFACTS, key, method, now).url

    return QuickTryPayload(
        quick_try_id=row.id,
        model=model_uploads.tool_model(version, card.architecture, presigner, now),
        spec=attack_catalog.spec_of(spec_row),
        levels=levels,
        image_url=url(original, "GET"),
        clean_upload_url=url(clean_key(row.id), "PUT"),
        level_upload_urls=[url(level_key(row.id, i), "PUT") for i in range(len(levels))],
    )


def apply_result(
    session: Session, job: m.ToolJob, report: QuickTryReport, buckets: storage.Buckets
) -> None:
    """Report phải đủ level theo đúng thứ tự payload, và ảnh đã được PUT trước khi gửi."""
    row = _row(session, job)
    expected: list[float] = job.payload["levels"]
    if [level.level for level in report.levels] != expected:
        raise Invalid(f"report.levels phải đúng các level {expected} theo thứ tự")
    keys = [clean_key(row.id), *(level_key(row.id, i) for i in range(len(expected)))]
    missing = [key for key in keys if not buckets.artifacts.exists(key)]
    if missing:
        raise Invalid(f"Chưa upload ảnh: {', '.join(missing)}")


# ---------------------------------------------------------------- dọn dẹp


def purge_expired(session: Session, buckets: storage.Buckets, now: datetime) -> int:
    """Xóa object MinIO của các lượt đã hết hạn, đặt `deleted_at`; job chưa xong chuyển `failed`.
    Trả số lượt đã dọn."""
    rows = session.scalars(
        select(m.QuickTry)
        .where(m.QuickTry.deleted_at.is_(None), m.QuickTry.expires_at <= now)
        .order_by(m.QuickTry.expires_at)
        .with_for_update(skip_locked=True)
    ).all()
    for row in rows:
        for key in buckets.artifacts.list(prefix(row.id)):
            buckets.artifacts.delete(key)
        job = session.get(m.ToolJob, row.tool_job_id, with_for_update=True)
        if job is not None and job.status in (ToolJobStatus.QUEUED, ToolJobStatus.RUNNING):
            tool_jobs.finish(job, now, error=EXPIRED_ERROR)
        row.deleted_at = now
    session.flush()
    return len(rows)


def purge_once(
    factory: sessionmaker[Session], buckets: storage.Buckets, clock: Clock = utcnow
) -> int:
    with factory.begin() as session:
        return purge_expired(session, buckets, clock())


async def purge_loop(
    factory: sessionmaker[Session],
    buckets: storage.Buckets,
    stop: asyncio.Event,
    interval_s: float = PURGE_INTERVAL_S,
) -> None:
    """Tác vụ nền của API: mỗi `interval_s` giây dọn lượt thử nhanh hết hạn. Lỗi của một vòng
    được ghi log, vòng sau chạy tiếp."""
    while not stop.is_set():
        try:
            count = await asyncio.to_thread(purge_once, factory, buckets)
            if count:
                logger.info("Đã dọn %d lượt thử nhanh hết hạn", count)
        except Exception:  # DB hay MinIO tạm lỗi không được làm dừng tác vụ dọn dẹp
            logger.exception("Vòng dọn thử nhanh lỗi; thử lại ở vòng sau")
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), interval_s)
