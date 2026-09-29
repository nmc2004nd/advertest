"""Nội dung email và gửi qua SMTP (validation.md Phase 5, `test_email.py`: nội dung, không có
ảnh hay dữ liệu dataset). Không cần DB; phần outbox ở tests/db/test_email_outbox.py."""

from __future__ import annotations

from email.message import EmailMessage
from types import TracebackType
from typing import Any, ClassVar

import pytest

from advertest_contracts.enums import ExperimentStatus, RunStatus
from backend.app.db import models as m
from backend.app.services import notifications as n

LINK = "http://localhost:5173/experiments/00000000-0000-5000-8000-000000000001"


def test_status_sentence_matches_spec_example() -> None:
    counts = {RunStatus.COMPLETED: 18, RunStatus.FAILED: 1, RunStatus.STOPPED_LIMIT: 1}
    assert n.status_sentence(counts) == "18/20 hoàn thành, 1 lỗi, 1 dừng do giới hạn"


def test_status_sentence_lists_every_non_zero_status() -> None:
    counts = {
        RunStatus.COMPLETED: 1, RunStatus.SKIPPED: 2, RunStatus.CANCELLED: 3,
        RunStatus.RUNNING: 1, RunStatus.QUEUED: 0,
    }  # fmt: skip
    assert n.status_sentence(counts) == "1/7 hoàn thành, 2 bỏ qua, 3 đã hủy, 1 đang chạy"


@pytest.mark.parametrize(
    ("status", "verb"),
    [(ExperimentStatus.COMPLETED, "đã hoàn thành"), (ExperimentStatus.CANCELLED, "đã bị hủy")],
)
def test_email_has_name_sentence_and_link(status: ExperimentStatus, verb: str) -> None:
    email = n.render_experiment_finished(
        to="an@x.test", name="PGD <b>&</b>", status=status,
        counts={RunStatus.COMPLETED: 2}, link=LINK,
    )  # fmt: skip
    assert email.subject == f'[AdverTest] Experiment "PGD <b>&</b>" {verb}'
    for body in (email.body_text, email.body_html):
        assert "2/2 hoàn thành" in body and LINK in body and verb in body
    # Tên do người dùng đặt được escape trong bản HTML.
    assert "PGD &lt;b&gt;&amp;&lt;/b&gt;" in email.body_html
    assert "<b>&</b>" not in email.body_html


def test_email_has_no_image_or_dataset_data() -> None:
    email = n.render_experiment_finished(
        to="an@x.test", name="x", status=ExperimentStatus.COMPLETED,
        counts={RunStatus.COMPLETED: 1}, link=LINK,
    )  # fmt: skip
    for body in (email.body_text, email.body_html):
        assert "/artifacts/" not in body and "<img" not in body and "s3://" not in body


class FakeSmtp:
    instances: ClassVar[list[FakeSmtp]] = []

    def __init__(self, host: str, port: int, timeout: float) -> None:
        self.address = (host, port, timeout)
        self.calls: list[tuple[str, Any]] = []
        FakeSmtp.instances.append(self)

    def __enter__(self) -> FakeSmtp:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.calls.append(("quit", None))

    def starttls(self) -> None:
        self.calls.append(("starttls", None))

    def login(self, user: str, password: str) -> None:
        self.calls.append(("login", (user, password)))

    def send_message(self, message: EmailMessage) -> None:
        self.calls.append(("send", message))


def _outbox() -> m.EmailOutbox:
    return m.EmailOutbox(
        to="an@x.test", subject="Tiêu đề", body_html="<p>html</p>", body_text="text"
    )


@pytest.mark.parametrize("secure", [False, True])
def test_smtp_sender_builds_multipart_message(secure: bool) -> None:
    FakeSmtp.instances.clear()
    config = n.SmtpConfig(
        host="mailpit", port=1025, sender="AdverTest <no-reply@x.test>",
        username="u" if secure else None, password="p" if secure else None, starttls=secure,
    )  # fmt: skip
    n.smtp_sender(config, connect=FakeSmtp)(_outbox())
    (client,) = FakeSmtp.instances
    assert client.address == ("mailpit", 1025, 30)
    names = [name for name, _ in client.calls]
    assert names == (["starttls", "login", "send", "quit"] if secure else ["send", "quit"])
    message = client.calls[names.index("send")][1]
    assert (message["To"], message["Subject"]) == ("an@x.test", "Tiêu đề")
    assert [part.get_content_type() for part in message.iter_parts()] == [
        "text/plain", "text/html",
    ]  # fmt: skip


def test_smtp_config_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SMTP_HOST", raising=False)
    assert n.SmtpConfig.from_env() is None
    monkeypatch.setenv("SMTP_HOST", "mailpit")
    monkeypatch.setenv("SMTP_PORT", "1025")
    monkeypatch.setenv("SMTP_STARTTLS", "true")
    config = n.SmtpConfig.from_env()
    assert config is not None and (config.host, config.port, config.starttls) == (
        "mailpit", 1025, True,
    )  # fmt: skip
