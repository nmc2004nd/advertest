"""validation.md Phase 5, Email (`test_email.py`)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.db import models as m
from backend.app.services import notifications

from .conftest import Api, attack, ok, post

pytestmark = pytest.mark.db


def _emails(engine: Engine, to: str) -> list[m.EmailOutbox]:
    with Session(engine) as session:
        return list(session.scalars(select(m.EmailOutbox).where(m.EmailOutbox.to == to)))


def test_completed_experiment_one_email_to_owner(
    api: Api, app_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP_BASE_URL", "https://advertest.example")
    target = api.target()
    api.profile(target, sec=0.05, batch=5, attacks=["fgsm"])
    _, email, client = api.user("engineer")
    created = ok(
        post(client, "/experiments", api.body(target, [attack("fgsm", [4])], name="Thử email"))
    ).json()
    assert _emails(app_engine, email) == []  # chưa kết thúc: chưa có email
    api.work(target, created["id"])
    (queued,) = _emails(app_engine, email)
    assert "Thử email" in queued.subject and "đã hoàn thành" in queued.subject
    link = f"https://advertest.example/experiments/{created['id']}"
    for body in (queued.body_text, queued.body_html):
        assert "1/1 hoàn thành" in body and link in body
        assert "/artifacts/" not in body and "s3://" not in body and "<img" not in body


def test_cancelled_experiment_emails_owner(api: Api, app_engine: Engine) -> None:
    _, email, client = api.user("engineer")
    created = ok(post(client, "/experiments", api.body(api.target(), [attack("fgsm", [4])]))).json()
    assert _emails(app_engine, email) == []
    ok(post(client, f"/experiments/{created['id']}/cancel"))
    (queued,) = _emails(app_engine, email)
    assert "đã bị hủy" in queued.subject


def test_smtp_failure_retried_then_failed_without_touching_experiment(
    api: Api, app_engine: Engine
) -> None:
    _, email, client = api.user("engineer")
    created = ok(post(client, "/experiments", api.body(api.target(), [attack("fgsm", [4])]))).json()
    ok(post(client, f"/experiments/{created['id']}/cancel"))
    attempts: list[str] = []

    def broken(outbox: m.EmailOutbox) -> None:
        if outbox.to == email:
            attempts.append(outbox.to)
            raise ConnectionRefusedError(111, "Connection refused")

    # Mốc đầu là lúc email tới hạn gửi (`next_attempt_at` mặc định `now()` của DB, giờ thật),
    # không phải đồng hồ giả: test không phụ thuộc ngày chạy (Phase 8 task 37).
    (queued,) = _emails(app_engine, email)
    now = [queued.next_attempt_at + timedelta(minutes=1)]
    for _ in range(10):  # đủ để qua mọi mốc backoff
        notifications.deliver_once(sessionmaker(app_engine), broken, lambda: now[0])
        now[0] += timedelta(minutes=10)
    (outbox,) = _emails(app_engine, email)
    assert (outbox.status, outbox.attempts, len(attempts)) == (m.EmailStatus.FAILED, 5, 5)
    assert outbox.last_error is not None and "Connection refused" in outbox.last_error
    assert client.get(f"/experiments/{created['id']}").json()["status"] == "cancelled"
