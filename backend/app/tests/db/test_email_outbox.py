"""Email qua outbox với Postgres và MinIO thật (validation.md Phase 5, `test_email.py`)."""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from advertest_contracts.enums import ExperimentStatus, Role
from backend.app.db import models as m
from backend.app.services import compute_targets, experiments, leasing, notifications, runs
from backend.app.storage import Buckets

from .conftest import make_user
from .test_worker_services import (
    T0,
    FakeClock,
    World,
    _completion,
    _config,
    _start_request,
    world,
)

pytestmark = pytest.mark.db
__all__ = ["world"]


def _owner_and_target(db: Session) -> tuple[m.User, m.ComputeTarget]:
    owner = make_user(db, role=Role.ENGINEER)
    admin = make_user(db)
    target = compute_targets.create(db, actor=admin, name=f"mail-{owner.id.hex[:8]}").target
    return owner, target


def _emails(engine: Engine, to: str) -> list[m.EmailOutbox]:
    with Session(engine) as session:
        return list(
            session.scalars(
                select(m.EmailOutbox).where(m.EmailOutbox.to == to).order_by(m.EmailOutbox.id)
            )
        )


def _submit(db: Session, owner: m.User, world: World, target: m.ComputeTarget) -> m.Experiment:
    return experiments.submit(
        db, actor=owner, config=_config(world), target=target, clock=FakeClock()
    )


def test_completed_experiment_queues_exactly_one_email(
    app_engine: Engine, world: World, buckets: Buckets, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP_BASE_URL", "https://advertest.example/")
    clock = FakeClock()
    with Session(app_engine) as db, db.begin():
        owner, target = _owner_and_target(db)
        experiment = _submit(db, owner, world, target)
        assert leasing.lease(db, target, clock) is experiment
        assert experiment.lease_id is not None
        planned = experiments.runs_of(db, experiment.id)
        for i, run in enumerate(planned):
            runs.start(db, target, run.id, _start_request(experiment.lease_id), clock)
            assert _emails(app_engine, owner.email) == []  # chưa kết thúc: chưa có email
            completion = _completion(run, experiment.lease_id, buckets)
            runs.complete(db, target, run.id, completion, buckets.artifacts.exists, clock)
            if i < len(planned) - 1:
                db.flush()
                assert (
                    db.scalar(select(m.EmailOutbox).where(m.EmailOutbox.to == owner.email)) is None
                )
        assert experiment.status == ExperimentStatus.COMPLETED
        experiment_id, name, email = experiment.id, experiment.name, owner.email
    (queued,) = _emails(app_engine, email)
    assert queued.status == m.EmailStatus.PENDING and queued.attempts == 0
    assert name in queued.subject and "đã hoàn thành" in queued.subject
    link = f"https://advertest.example/experiments/{experiment_id}"
    total = len(planned)
    for body in (queued.body_text, queued.body_html):
        assert f"{total}/{total} hoàn thành" in body and link in body
        assert "/artifacts/" not in body and "s3://" not in body and "<img" not in body


def test_cancelled_experiment_queues_email_in_same_transaction(
    app_engine: Engine, world: World
) -> None:
    with Session(app_engine) as db, db.begin():
        owner, target = _owner_and_target(db)
        experiment = _submit(db, owner, world, target)
        experiment_id, email, owner_id = experiment.id, owner.email, owner.id
    assert _emails(app_engine, email) == []  # queued: chưa kết thúc

    # Transaction hủy bị rollback: không có email, experiment vẫn queued.
    with Session(app_engine) as db:
        actor = db.get(m.User, owner_id)
        assert actor is not None
        experiments.cancel(db, actor=actor, experiment_id=experiment_id, clock=FakeClock())
        db.rollback()
        still = db.get(m.Experiment, experiment_id)
        assert still is not None and still.status == ExperimentStatus.QUEUED
    assert _emails(app_engine, email) == []

    with Session(app_engine) as db, db.begin():
        actor = db.get(m.User, owner_id)
        assert actor is not None
        experiments.cancel(db, actor=actor, experiment_id=experiment_id, clock=FakeClock())
    (queued,) = _emails(app_engine, email)
    assert "đã bị hủy" in queued.subject
    assert "0/3 hoàn thành, 3 đã hủy" in queued.body_text  # _config: fgsm [4, 8], pgd [4]


def _pending_email(app_engine: Engine) -> tuple[UUID, str]:
    with Session(app_engine) as db, db.begin():
        owner = make_user(db, role=Role.ENGINEER)
        row = m.EmailOutbox(
            to=owner.email, subject="s", body_html="<p>b</p>", body_text="b",
            next_attempt_at=T0,
        )  # fmt: skip
        db.add(row)
        db.flush()
        return row.id, owner.email


def _deliver(app_engine: Engine, send: notifications.SendFn, clock: FakeClock) -> None:
    notifications.deliver_once(sessionmaker(app_engine), send, clock)


def test_failed_smtp_is_retried_with_backoff_then_marked_failed(app_engine: Engine) -> None:
    email_id, to = _pending_email(app_engine)
    attempts: list[str] = []

    def broken(email: m.EmailOutbox) -> None:
        if email.to == to:
            attempts.append(email.to)
            raise ConnectionRefusedError(111, "Connection refused")

    clock = FakeClock()
    for waited in (0, 30, 60, 120, 240):
        clock.advance(waited - 1)
        before = len(attempts)
        _deliver(app_engine, broken, clock)
        assert len(attempts) == before  # chưa đến hạn (thiếu 1 giây): không gửi
        clock.advance(1)
        _deliver(app_engine, broken, clock)
        assert len(attempts) == before + 1
    with Session(app_engine) as db:
        email = db.get(m.EmailOutbox, email_id)
        assert email is not None
        assert (email.status, email.attempts) == (m.EmailStatus.FAILED, 5)
        assert email.last_error is not None and "Connection refused" in email.last_error
        assert email.sent_at is None
    clock.advance(10_000)
    _deliver(app_engine, broken, clock)
    assert len(attempts) == 5  # failed: không thử nữa


def test_retry_then_success_marks_sent(app_engine: Engine) -> None:
    email_id, to = _pending_email(app_engine)
    outcomes = [RuntimeError("SMTP tạm lỗi"), None]

    def flaky(email: m.EmailOutbox) -> None:
        if email.to == to:
            outcome = outcomes.pop(0)
            if outcome is not None:
                raise outcome

    clock = FakeClock()
    _deliver(app_engine, flaky, clock)
    clock.advance(30)
    _deliver(app_engine, flaky, clock)
    with Session(app_engine) as db:
        email = db.get(m.EmailOutbox, email_id)
        assert email is not None
        assert (email.status, email.attempts) == (m.EmailStatus.SENT, 2)
        assert email.sent_at == T0 + timedelta(seconds=30)
        assert email.last_error == "RuntimeError: SMTP tạm lỗi"  # lỗi cũ giữ để tra cứu


def test_smtp_failure_does_not_touch_experiment_status(app_engine: Engine, world: World) -> None:
    with Session(app_engine) as db, db.begin():
        owner, target = _owner_and_target(db)
        experiment = _submit(db, owner, world, target)
        experiments.cancel(db, actor=owner, experiment_id=experiment.id, clock=FakeClock())
        experiment_id, to = experiment.id, owner.email

    def broken(email: m.EmailOutbox) -> None:
        if email.to == to:
            raise OSError("SMTP không tới được")

    clock = FakeClock()
    clock.now = T0 + timedelta(days=365)  # email đến hạn
    _deliver(app_engine, broken, clock)
    with Session(app_engine) as db:
        after = db.get(m.Experiment, experiment_id)
        assert after is not None and after.status == ExperimentStatus.CANCELLED
    (email,) = _emails(app_engine, to)
    assert email.status == m.EmailStatus.PENDING and email.attempts == 1
