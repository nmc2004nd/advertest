"""Ảnh failure case cho giao diện (requirements.md Phase 5, Hiển thị ảnh và quyền riêng tư).

- URL tạm thời `/artifacts/<token>`: token ký HMAC-SHA256 gồm khóa của đúng một đối tượng trong
  bucket artifacts và thời điểm hết hạn (10 phút). API stream ảnh từ MinIO bằng thông tin đăng
  nhập của mình; MinIO không mở ra ngoài. Route còn đòi phiên có `experiment.read`.
- Dataset chưa làm mờ (`anonymized = false`): mặc định không cấp URL nào
  (`hidden_unanonymized`); khi server bật `DEV_ALLOW_UNBLURRED=true` thì cấp URL kèm
  `dev_unblurred` để giao diện hiện dải cảnh báo. Không bật cờ này ở môi trường demo.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import logging
import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import cache
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from advertest_contracts.enums import DisplayMode
from advertest_contracts.models import FailureCaseUrls, FailureCaseView
from backend.app.db import models as m
from backend.app.services.errors import NotFound

logger = logging.getLogger(__name__)

TOKEN_TTL = timedelta(minutes=10)
SECRET_ENV = "ARTIFACT_TOKEN_SECRET"
DEV_FLAG_ENV = "DEV_ALLOW_UNBLURRED"
# Chỉ ký cho ảnh của run (runs/<run_id>/...) và ảnh kết quả thử nhanh (Phase R2,
# quick-tries/<id>/...): token không mở được đối tượng khác trong bucket.
ALLOWED_PREFIXES = ("runs/", "quick-tries/")
# Ảnh gốc của thử nhanh (chưa làm mờ) không bao giờ được phục vụ qua API.
QUICK_TRY_ORIGINAL = "original"
MEDIA_TYPES = {".png": "image/png", ".webp": "image/webp"}
THUMBS = ("clean_thumb", "adversarial_thumb")


@cache
def _fallback_secret() -> bytes:
    logger.warning(
        "Thiếu %s: dùng khóa ngẫu nhiên của tiến trình; URL ảnh mất hiệu lực khi API khởi động"
        " lại và sai nếu chạy nhiều tiến trình",
        SECRET_ENV,
    )
    return secrets.token_bytes(32)


def _secret() -> bytes:
    value = os.environ.get(SECRET_ENV)
    return value.encode() if value else _fallback_secret()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _sign(payload: bytes) -> bytes:
    return hmac.new(_secret(), payload, hashlib.sha256).digest()


def servable(key: str) -> bool:
    if key.startswith("quick-tries/"):
        return not key.rsplit("/", 1)[-1].startswith(QUICK_TRY_ORIGINAL)
    return key.startswith(ALLOWED_PREFIXES)


def issue(key: str, now: datetime) -> tuple[str, datetime]:
    """Token cho khóa `key`, hết hạn sau 10 phút (làm tròn xuống giây)."""
    if not servable(key):
        raise ValueError(f"Không cấp URL cho khóa ngoài {ALLOWED_PREFIXES}: {key}")
    expires_at = (now + TOKEN_TTL).replace(microsecond=0)
    payload = f"{int(expires_at.timestamp())}:{key}".encode()
    return f"{_b64(payload)}.{_b64(_sign(payload))}", expires_at


def verify(token: str, now: datetime) -> str | None:
    """Khóa của đối tượng nếu token đúng chữ ký và chưa hết hạn; ngược lại `None`."""
    try:
        encoded, signature = token.split(".", 1)
        payload = _unb64(encoded)
        if not hmac.compare_digest(_sign(payload), _unb64(signature)):
            return None
        expires, key = payload.decode().split(":", 1)
        expires_at = datetime.fromtimestamp(int(expires), UTC)
    except (ValueError, binascii.Error, UnicodeDecodeError):
        return None
    if now >= expires_at or not servable(key):
        return None
    return key


def media_type(key: str) -> str:
    return next(
        (t for ext, t in MEDIA_TYPES.items() if key.endswith(ext)), "application/octet-stream"
    )


# ---------------------------------------------------------------- failure case


def dev_unblurred_allowed() -> bool:
    return os.environ.get(DEV_FLAG_ENV, "").strip().lower() in ("1", "true", "yes")


def display_mode(session: Session, run: m.Run) -> DisplayMode:
    anonymized = session.scalar(
        select(m.Dataset.anonymized)
        .join(m.DatasetVersion, m.DatasetVersion.dataset_id == m.Dataset.id)
        .join(m.Slice, m.Slice.dataset_version_id == m.DatasetVersion.id)
        .join(m.Experiment, m.Experiment.slice_id == m.Slice.id)
        .where(m.Experiment.id == run.experiment_id)
    )
    if anonymized:
        return DisplayMode.NORMAL
    return DisplayMode.DEV_UNBLURRED if dev_unblurred_allowed() else DisplayMode.HIDDEN_UNANONYMIZED


@dataclass(frozen=True)
class _Issued:
    urls: FailureCaseUrls
    expires_at: datetime | None


def _urls(
    artifacts: dict[str, str | None], mode: DisplayMode, full: bool, now: datetime
) -> _Issued:
    if mode == DisplayMode.HIDDEN_UNANONYMIZED:
        return _Issued(
            FailureCaseUrls.model_validate(dict.fromkeys(FailureCaseUrls.model_fields)), None
        )
    keys = {
        "clean": artifacts.get("clean_png"),
        "adversarial": artifacts.get("adversarial_png"),
        "perturbation": artifacts.get("perturbation_png"),
        # Case cũ không có thumbnail: dùng ảnh gốc.
        "clean_thumb": artifacts.get("clean_thumb") or artifacts.get("clean_png"),
        "adversarial_thumb": artifacts.get("adversarial_thumb") or artifacts.get("adversarial_png"),
    }
    urls: dict[str, str | None] = {}
    expires_at: datetime | None = None
    for name, key in keys.items():
        if key is None or (not full and name not in THUMBS):
            urls[name] = None
            continue
        token, expires_at = issue(key, now)
        urls[name] = f"/artifacts/{token}"
    return _Issued(FailureCaseUrls.model_validate(urls), expires_at)


def case_mode(case: m.FailureCase, dataset_mode: DisplayMode) -> DisplayMode:
    """Phase 6 (plan task 28): case đã làm mờ thì hiển thị bình thường dù dataset chưa ẩn danh;
    case cũ (chưa làm mờ) theo quy tắc của dataset."""
    anonymization = case.anonymization or {}
    return DisplayMode.NORMAL if anonymization.get("applied") else dataset_mode


def _view(case: m.FailureCase, mode: DisplayMode, full: bool, now: datetime) -> FailureCaseView:
    mode = case_mode(case, mode)
    issued = _urls(case.artifacts, mode, full, now)
    return FailureCaseView.model_validate(
        {
            "id": case.id,
            "run_id": case.run_id,
            "fingerprint": case.fingerprint,
            "image_id": case.image_id,
            "lost_objects": case.lost_objects,
            "new_false_positives": case.new_false_positives,
            "severity_score": case.severity_score,
            "detections": case.detections,
            # Đề xuất contract 002: ảnh bị ẩn thì không trả khóa MinIO.
            "artifacts": None if mode == DisplayMode.HIDDEN_UNANONYMIZED else case.artifacts,
            "anonymization": case.anonymization,
            "perturbation_kind": case.perturbation_kind or "amplified_noise",
            "urls": issued.urls,
            "urls_expire_at": issued.expires_at,
            "display_mode": mode,
        }
    )


def list_cases(session: Session, run_id: UUID, now: datetime) -> list[FailureCaseView]:
    """Failure case của run (run `cached` dùng case của run gốc), `severity_score` giảm dần; chỉ
    có URL thumbnail."""
    run = session.get(m.Run, run_id)
    if run is None:
        raise NotFound("Không có run này")
    source = run.cached_from_run_id or run.id
    mode = display_mode(session, run)
    cases = session.scalars(
        select(m.FailureCase)
        .where(m.FailureCase.run_id == source)
        .order_by(m.FailureCase.severity_score.desc(), m.FailureCase.rank)
    )
    return [_view(case, mode, False, now) for case in cases]


def get_case(session: Session, case_id: UUID, now: datetime) -> FailureCaseView:
    case = session.get(m.FailureCase, case_id)
    if case is None:
        raise NotFound("Không có failure case này")
    run = session.get(m.Run, case.run_id)
    assert run is not None  # khóa ngoại
    return _view(case, display_mode(session, run), True, now)
