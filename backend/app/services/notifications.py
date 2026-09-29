"""Email khi experiment kết thúc, qua outbox (requirements.md Phase 5, Email).

- `enqueue_experiment_finished` thêm email vào `email_outbox` trong cùng transaction với việc
  đổi trạng thái experiment sang `completed` hoặc `cancelled`: trạng thái không phụ thuộc SMTP.
- `deliver_due` gửi email đến hạn; lỗi thì thử lại với backoff, tối đa 5 lần, lỗi cuối ghi vào
  `last_error`. Nhiều tiến trình API chạy cùng lúc không gửi trùng (`FOR UPDATE SKIP LOCKED`).
- Email chỉ có tên experiment, câu tóm tắt trạng thái và link; không có ảnh hay dữ liệu dataset.
"""

from __future__ import annotations

import asyncio
import contextlib
import html
import logging
import os
import smtplib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.message import EmailMessage
from types import TracebackType
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from advertest_contracts.enums import ExperimentStatus, RunStatus
from backend.app.db import models as m
from backend.app.services.clock import Clock, utcnow

MAX_ATTEMPTS = 5
# Chờ trước lần thử thứ 2, 3, 4, 5 (sau lần lỗi thứ 1, 2, 3, 4).
BACKOFF = (
    timedelta(seconds=30),
    timedelta(seconds=60),
    timedelta(seconds=120),
    timedelta(seconds=240),
)
BATCH = 20
DEFAULT_APP_BASE_URL = "http://localhost:5173"
FINISHED = {ExperimentStatus.COMPLETED: "đã hoàn thành", ExperimentStatus.CANCELLED: "đã bị hủy"}
# Thứ tự và nhãn các phần của câu tóm tắt (sau "x/y hoàn thành").
PARTS = (
    (RunStatus.FAILED, "lỗi"),
    (RunStatus.STOPPED_LIMIT, "dừng do giới hạn"),
    (RunStatus.SKIPPED, "bỏ qua"),
    (RunStatus.CANCELLED, "đã hủy"),
    (RunStatus.RUNNING, "đang chạy"),
    (RunStatus.QUEUED, "chưa chạy"),
)


def app_base_url() -> str:
    return os.environ.get("APP_BASE_URL", DEFAULT_APP_BASE_URL).rstrip("/")


def status_sentence(counts: dict[RunStatus, int]) -> str:
    """Ví dụ "18/20 hoàn thành, 1 lỗi, 1 dừng do giới hạn"; bỏ phần bằng 0."""
    total = sum(counts.values())
    parts = [f"{counts.get(RunStatus.COMPLETED, 0)}/{total} hoàn thành"]
    parts += [f"{counts[status]} {label}" for status, label in PARTS if counts.get(status, 0)]
    return ", ".join(parts)


@dataclass(frozen=True)
class Email:
    to: str
    subject: str
    body_html: str
    body_text: str


def render_experiment_finished(
    *, to: str, name: str, status: ExperimentStatus, counts: dict[RunStatus, int], link: str
) -> Email:
    verb = FINISHED[status]
    sentence = status_sentence(counts)
    text = (
        f'Experiment "{name}" {verb}.\n\n'
        f"Kết quả các run: {sentence}.\n\n"
        f"Xem chi tiết: {link}\n\n"
        "Email tự động từ AdverTest. Kết quả chưa được duyệt.\n"
    )
    body_html = (
        '<!doctype html><html lang="vi"><body style="font-family: sans-serif">'
        f"<p>Experiment <strong>{html.escape(name)}</strong> {verb}.</p>"
        f"<p>Kết quả các run: {html.escape(sentence)}.</p>"
        f'<p><a href="{html.escape(link, quote=True)}">Xem chi tiết experiment</a></p>'
        '<p style="color: #666; font-size: 12px">'
        "Email tự động từ AdverTest. Kết quả chưa được duyệt.</p>"
        "</body></html>"
    )
    return Email(to=to, subject=f"[AdverTest] Experiment \"{name}\" {verb}", body_html=body_html,
                 body_text=text)  # fmt: skip


def enqueue_experiment_finished(session: Session, experiment: m.Experiment) -> m.EmailOutbox:
    """Thêm email "experiment kết thúc" cho chủ sở hữu vào outbox (gọi trong transaction đổi
    trạng thái sang `completed` hoặc `cancelled`)."""
    owner = session.get(m.User, experiment.created_by)
    assert owner is not None  # khóa ngoại
    session.flush()  # trạng thái run vừa đổi phải được đếm
    rows = session.execute(
        select(m.Run.status, func.count())
        .where(m.Run.experiment_id == experiment.id)
        .group_by(m.Run.status)
    )
    counts = {status: count for status, count in rows}
    email = render_experiment_finished(
        to=owner.email,
        name=experiment.name,
        status=experiment.status,
        counts=counts,
        link=f"{app_base_url()}/experiments/{experiment.id}",
    )
    row = m.EmailOutbox(
        to=email.to, subject=email.subject, body_html=email.body_html, body_text=email.body_text
    )
    session.add(row)
    session.flush()
    return row


# ---------------------------------------------------------------- gửi


SendFn = Callable[[m.EmailOutbox], None]


@dataclass(frozen=True)
class SmtpConfig:
    host: str
    port: int
    sender: str
    username: str | None
    password: str | None
    starttls: bool
    timeout_s: float = 30

    @classmethod
    def from_env(cls) -> SmtpConfig | None:
        """`None` khi chưa cấu hình `SMTP_HOST`: email nằm chờ trong outbox."""
        host = os.environ.get("SMTP_HOST")
        if not host:
            return None
        return cls(
            host=host,
            port=int(os.environ.get("SMTP_PORT", "25")),
            sender=os.environ.get("SMTP_FROM", "AdverTest <no-reply@advertest.local>"),
            username=os.environ.get("SMTP_USERNAME") or None,
            password=os.environ.get("SMTP_PASSWORD") or None,
            starttls=os.environ.get("SMTP_STARTTLS", "false").strip().lower() in ("1", "true"),
        )


def message_of(email: m.EmailOutbox, sender: str) -> EmailMessage:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = email.to
    message["Subject"] = email.subject
    message.set_content(email.body_text)
    message.add_alternative(email.body_html, subtype="html")
    return message


class SmtpClient(Protocol):
    """Phần của `smtplib.SMTP` mà việc gửi dùng (test thay bằng client giả)."""

    def __enter__(self) -> SmtpClient: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> object: ...

    def starttls(self) -> object: ...

    def login(self, user: str, password: str) -> object: ...

    def send_message(self, msg: EmailMessage) -> object: ...


def smtp_sender(config: SmtpConfig, connect: Callable[..., SmtpClient] = smtplib.SMTP) -> SendFn:
    def send(email: m.EmailOutbox) -> None:
        with connect(config.host, config.port, timeout=config.timeout_s) as client:
            if config.starttls:
                client.starttls()
            if config.username and config.password:
                client.login(config.username, config.password)
            client.send_message(message_of(email, config.sender))

    return send


def _error_text(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"[:2000]


def deliver_due(session: Session, send: SendFn, now: datetime, limit: int = BATCH) -> int:
    """Gửi các email `pending` đã đến hạn; trả số email đã xử lý (gửi được hoặc lỗi)."""
    emails = list(
        session.scalars(
            select(m.EmailOutbox)
            .where(
                m.EmailOutbox.status == m.EmailStatus.PENDING,
                m.EmailOutbox.next_attempt_at <= now,
            )
            .order_by(m.EmailOutbox.next_attempt_at, m.EmailOutbox.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    )
    for email in emails:
        email.attempts += 1
        try:
            send(email)
        except Exception as exc:  # mọi lỗi gửi đều được ghi lại và thử lại, không làm dừng vòng
            email.last_error = _error_text(exc)
            if email.attempts >= MAX_ATTEMPTS:
                email.status = m.EmailStatus.FAILED
            else:
                email.next_attempt_at = now + BACKOFF[email.attempts - 1]
        else:
            email.status = m.EmailStatus.SENT
            email.sent_at = now
        session.flush()
    return len(emails)


# ---------------------------------------------------------------- vòng gửi trong API

logger = logging.getLogger(__name__)
LOOP_INTERVAL_S = 10.0


def deliver_once(factory: sessionmaker[Session], send: SendFn, clock: Clock = utcnow) -> int:
    with factory.begin() as session:
        return deliver_due(session, send, clock())


async def delivery_loop(
    factory: sessionmaker[Session],
    send: SendFn,
    stop: asyncio.Event,
    interval_s: float = LOOP_INTERVAL_S,
) -> None:
    """Tác vụ nền của API: mỗi `interval_s` giây gửi các email đến hạn (SMTP chạy trong thread,
    không chặn event loop). Lỗi của một vòng được ghi log, vòng sau chạy tiếp."""
    while not stop.is_set():
        try:
            await asyncio.to_thread(deliver_once, factory, send)
        except Exception:  # lỗi DB tạm thời không được làm dừng tác vụ gửi email
            logger.exception("Vòng gửi email lỗi; thử lại ở vòng sau")
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), interval_s)
