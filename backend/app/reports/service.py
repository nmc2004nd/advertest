"""Sinh, lưu, tải và xác minh report chính thức (requirements.md Phase 8, mục Report; plan task 22,
23).

- `create_pending`: report `generating` tạo trong cùng giao dịch với quyết định `approve`.
- `generate`: tác vụ nền sau khi giao dịch đó commit. Mỗi lần thử ghi snapshot, JSON
  (`canonical_json` của snapshot) và PDF vào `reports/<report_id>/a<lần thử>/` (store không cho
  ghi đè); thành công → `ready` kèm hai hash; lỗi 3 lần → `failed` (experiment vẫn `approved`).
- `resume_generating`: lúc API khởi động, sinh tiếp report kẹt ở `generating` (kickoff).
- Tải xuống chỉ trả file đã lưu (mọi bản tải cùng hash), qua URL có token HMAC 10 phút.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from advertest_contracts.enums import ReportStatus
from advertest_contracts.hashing import canonical_json
from advertest_contracts.models import (
    ReportDetail,
    ReportDownload,
    ReportSnapshot,
    ReportView,
    VerifyInfo,
)
from backend.app.db import models as m
from backend.app.reports import render, snapshot
from backend.app.reports.views import view
from backend.app.services import artifacts as artifact_tokens
from backend.app.services import audit
from backend.app.services.clock import Clock, utcnow
from backend.app.services.errors import Conflict, NotFound
from ml_core.store import KeyNotFoundError

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
TOKEN_TTL = timedelta(minutes=10)
Format = Literal["pdf", "json"]
MEDIA_TYPES: dict[Format, str] = {"pdf": "application/pdf", "json": "application/json"}
ENTITY = "report"


@dataclass(frozen=True)
class Stores:
    """`read_artifact` đọc bucket artifacts (manifest, thumbnail); `put`/`get` là bucket reports."""

    read_artifact: Callable[[str], bytes]
    put: Callable[[str, bytes], None]
    get: Callable[[str], bytes]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------- sinh report (task 22)


def create_pending(session: Session, experiment: m.Experiment, approver_id: UUID) -> m.Report:
    report = m.Report(experiment_id=experiment.id, approved_by=approver_id)
    session.add(report)
    session.flush()
    return report


def _attempt(session: Session, stores: Stores, report: m.Report, clock: Clock) -> None:
    snap = snapshot.build(session, stores.read_artifact, report)
    json_bytes = canonical_json(snap).encode()
    pdf_bytes = render.pdf(render.html(snap, stores.read_artifact))
    prefix = f"{report.id}/a{report.attempts}"
    keys = {
        "snapshot": f"{prefix}/snapshot.json",
        "json": f"{prefix}/report.json",
        "pdf": f"{prefix}/report.pdf",
    }
    stores.put(keys["snapshot"], snap.model_dump_json().encode())
    stores.put(keys["json"], json_bytes)
    stores.put(keys["pdf"], pdf_bytes)
    report.snapshot_key, report.json_key, report.pdf_key = (
        keys["snapshot"],
        keys["json"],
        keys["pdf"],
    )
    report.json_sha256 = _sha256(json_bytes)
    report.pdf_sha256 = _sha256(pdf_bytes)
    report.generated_at = clock()
    report.status = ReportStatus.READY
    audit.record(
        session,
        actor=None,
        action="report.generated",
        entity_type=ENTITY,
        entity_id=report.id,
        after={
            "experiment_id": str(report.experiment_id),
            "json_sha256": report.json_sha256,
            "pdf_sha256": report.pdf_sha256,
            "attempts": report.attempts,
        },
    )


def generate(
    factory: sessionmaker[Session], stores: Stores, report_id: UUID, clock: Clock = utcnow
) -> ReportStatus | None:
    """Thử tối đa `MAX_ATTEMPTS` lần; trả trạng thái cuối (None khi report không còn ở
    `generating`, ví dụ tiến trình khác đã sinh xong)."""
    last_error = ""
    for _ in range(MAX_ATTEMPTS):
        with factory.begin() as session:  # đếm lần thử trước, kể cả khi lần này lỗi
            report = session.get(m.Report, report_id, with_for_update=True)
            if report is None or report.status != ReportStatus.GENERATING:
                return None
            report.attempts += 1
        try:
            with factory.begin() as session:
                report = session.get(m.Report, report_id, with_for_update=True)
                assert report is not None
                _attempt(session, stores, report, clock)
            return ReportStatus.READY
        except Exception as exc:  # lỗi bất kỳ của dựng, render, lưu: thử lại rồi ghi failed
            last_error = f"{type(exc).__name__}: {exc}"[:500]
            logger.exception("Sinh report %s lỗi", report_id)
    with factory.begin() as session:
        report = session.get(m.Report, report_id, with_for_update=True)
        assert report is not None
        report.status = ReportStatus.FAILED
        audit.record(
            session,
            actor=None,
            action="report.generation_failed",
            entity_type=ENTITY,
            entity_id=report.id,
            after={"attempts": report.attempts, "error": last_error},
        )
    return ReportStatus.FAILED


def regenerate(session: Session, report_id: UUID) -> ReportView:
    """Chỉ khi `failed` (409 nếu khác); giữ nguyên `report_id`. Gọi `generate` sau commit."""
    report = session.get(m.Report, report_id, with_for_update=True)
    if report is None:
        raise NotFound("Không có report này")
    if report.status != ReportStatus.FAILED:
        raise Conflict(f"Report đang ở trạng thái {report.status}; chỉ sinh lại được khi failed")
    report.status = ReportStatus.GENERATING
    session.flush()
    return view(session, report)


def resume_generating(factory: sessionmaker[Session], stores: Stores, clock: Clock = utcnow) -> int:
    """Lúc khởi động: sinh tiếp mọi report còn `generating` (tác vụ nền trước bị ngắt)."""
    with factory.begin() as session:
        ids = list(
            session.scalars(select(m.Report.id).where(m.Report.status == ReportStatus.GENERATING))
        )
    for report_id in ids:
        generate(factory, stores, report_id, clock)
    return len(ids)


# ---------------------------------------------------------------- đọc (task 23)


def list_reports(session: Session) -> list[ReportView]:
    rows = session.scalars(select(m.Report).order_by(m.Report.created_at.desc(), m.Report.id))
    return [view(session, row) for row in rows]


def _get(session: Session, report_id: UUID) -> m.Report:
    report = session.get(m.Report, report_id)
    if report is None:
        raise NotFound("Không có report này")
    return report


def detail(session: Session, stores: Stores, report_id: UUID) -> ReportDetail:
    """Report trong ứng dụng; snapshot đọc từ file đã lưu (không dựng lại)."""
    report = _get(session, report_id)
    snap = None
    if report.status == ReportStatus.READY:
        assert report.snapshot_key is not None
        snap = ReportSnapshot.model_validate_json(stores.get(report.snapshot_key))
    return ReportDetail(report=view(session, report), snapshot=snap)


def download(
    session: Session, *, actor: m.User, report_id: UUID, fmt: Format, now: datetime
) -> ReportDownload:
    report = _get(session, report_id)
    if report.status != ReportStatus.READY:
        raise Conflict(f"Report đang ở trạng thái {report.status}; chưa tải được")
    key = report.pdf_key if fmt == "pdf" else report.json_key
    sha = report.pdf_sha256 if fmt == "pdf" else report.json_sha256
    assert key is not None and sha is not None  # ràng buộc ready_has_files
    token, expires_at = _issue(key, now)
    audit.record(
        session,
        actor=actor,
        action="report.downloaded",
        entity_type=ENTITY,
        entity_id=report.id,
        after={"format": fmt, "sha256": sha},
    )
    return ReportDownload(
        format=fmt,
        url=f"/reports/files/{token}",
        expires_at=expires_at,
        sha256=sha,
        filename=f"report-{report.id}.{fmt}",
    )


def verify_info(session: Session, report_id: UUID) -> VerifyInfo:
    """Công khai: chỉ report `ready`, không có tên người hay nội dung (404 với trạng thái khác)."""
    report = session.get(m.Report, report_id)
    if report is None or report.status != ReportStatus.READY:
        raise NotFound("Không có report đã phát hành với mã này")
    assert report.generated_at and report.json_sha256 and report.pdf_sha256
    return VerifyInfo(
        report_id=report.id,
        issued_at=report.generated_at,
        json_sha256=report.json_sha256,
        pdf_sha256=report.pdf_sha256,
    )


# ---------------------------------------------------------------- token tải file


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _sign(payload: bytes) -> bytes:
    # Cùng khóa bí mật với URL ảnh (ARTIFACT_TOKEN_SECRET); tiền tố tách hai loại token.
    return hmac.new(artifact_tokens._secret(), b"report:" + payload, hashlib.sha256).digest()


def _issue(key: str, now: datetime) -> tuple[str, datetime]:
    expires_at = now + TOKEN_TTL
    payload = f"{int(expires_at.timestamp())}:{key}".encode()
    return f"{_b64(payload)}.{_b64(_sign(payload))}", expires_at


def read_file(stores: Stores, token: str, now: datetime) -> tuple[bytes, str, str]:
    """(nội dung, media type, tên file) của token còn hạn; sai, sửa hoặc hết hạn → NotFound."""
    try:
        payload_b64, signature_b64 = token.split(".", 1)
        payload = _unb64(payload_b64)
        signature = _unb64(signature_b64)
        expires_s, key = payload.decode().split(":", 1)
        expires = int(expires_s)
    except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
        raise NotFound("Không tìm thấy file") from exc
    if not hmac.compare_digest(signature, _sign(payload)) or expires < now.timestamp():
        raise NotFound("Không tìm thấy file")
    fmt: Format = "pdf" if key.endswith(".pdf") else "json"
    try:
        data = stores.get(key)
    except KeyNotFoundError as exc:
        raise NotFound("Không tìm thấy file") from exc
    report_id = key.split("/", 1)[0]
    return data, MEDIA_TYPES[fmt], f"report-{report_id}.{fmt}"
