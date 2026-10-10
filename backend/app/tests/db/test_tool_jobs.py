"""Hàng đợi job công cụ (requirements.md Phase R2, mục Job công cụ): thứ tự lease, mất lease,
heartbeat bằng lease cũ, máy thuê không nhận job."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from advertest_contracts.enums import BillingMode, ComputeKind, ToolJobKind, ToolJobStatus
from backend.app.db import models as m
from backend.app.services import tool_jobs
from backend.app.services.errors import Conflict

pytestmark = pytest.mark.db

T0 = datetime(2026, 10, 10, 8, tzinfo=UTC)


@pytest.fixture
def session(app_engine: Engine) -> Iterator[Session]:
    """Mọi thay đổi bị rollback: job của test không lọt sang test khác (lease lấy job toàn cục)."""
    with Session(app_engine) as s:
        s.begin()
        yield s
        s.rollback()


def _target(session: Session, kind: ComputeKind = ComputeKind.LOCAL) -> m.ComputeTarget:
    rented = kind == ComputeKind.RENTED
    target = m.ComputeTarget(
        name=f"tools-{uuid.uuid4().hex[:8]}",
        kind=kind,
        billing_mode=BillingMode.HOURLY if rented else BillingMode.NONE,
        price_per_hour=Decimal("1.0") if rented else None,
        currency="USD" if rented else None,
    )
    session.add(target)
    session.flush()
    return target


def _enqueue(session: Session, kind: ToolJobKind, at: datetime) -> m.ToolJob:
    return tool_jobs.enqueue(session, kind, {"n": at.isoformat()}, created_by=None, now=at)


class Failed:
    def __init__(self) -> None:
        self.jobs: list[m.ToolJob] = []

    def __call__(self, session: Session, job: m.ToolJob, now: datetime) -> None:
        self.jobs.append(job)


def test_quick_try_leased_before_older_checks(session: Session) -> None:
    target = _target(session)
    spec = _enqueue(session, ToolJobKind.SPEC_CHECK, T0)
    model = _enqueue(session, ToolJobKind.MODEL_CHECK, T0 + timedelta(seconds=1))
    quick = _enqueue(session, ToolJobKind.QUICK_TRY, T0 + timedelta(seconds=2))
    now = T0 + timedelta(seconds=3)
    leased = [tool_jobs.lease(session, target, now, Failed()) for _ in range(4)]
    assert [job.id if job else None for job in leased] == [quick.id, spec.id, model.id, None]
    first = leased[0]
    assert first is not None and first.status == ToolJobStatus.RUNNING
    assert first.leased_by == target.id and first.attempts == 1
    assert first.lease_expires_at == now + timedelta(seconds=tool_jobs.LEASE_SECONDS)


def test_lost_lease_requeued_twice_then_failed(session: Session) -> None:
    target = _target(session)
    job = _enqueue(session, ToolJobKind.QUICK_TRY, T0)
    failed = Failed()
    now = T0
    leases = []
    for attempt in range(1, tool_jobs.MAX_ATTEMPTS + 1):
        leased = tool_jobs.lease(session, target, now, failed)
        assert leased is not None and leased.id == job.id and leased.attempts == attempt
        leases.append(leased.lease_id)
        # Lease còn hạn: không ai khác nhận được.
        assert tool_jobs.lease(session, target, now + timedelta(seconds=59), failed) is None
        now += timedelta(seconds=tool_jobs.LEASE_SECONDS + 1)
    assert len(set(leases)) == tool_jobs.MAX_ATTEMPTS
    assert tool_jobs.lease(session, target, now, failed) is None
    assert job.status == ToolJobStatus.FAILED and job.error == tool_jobs.LOST_LEASE_ERROR
    assert failed.jobs == [job]
    last = leases[-1]
    assert last is not None
    with pytest.raises(Conflict):
        tool_jobs.heartbeat(session, target, job.id, last, now)


def test_heartbeat_extends_and_old_lease_conflicts(session: Session) -> None:
    target = _target(session)
    job = _enqueue(session, ToolJobKind.SPEC_CHECK, T0)
    first = tool_jobs.lease(session, target, T0, Failed())
    assert first is not None and first.lease_id is not None
    old = first.lease_id
    tool_jobs.heartbeat(session, target, job.id, old, T0 + timedelta(seconds=50))
    assert job.lease_expires_at == T0 + timedelta(seconds=110)
    later = T0 + timedelta(seconds=111)
    again = tool_jobs.lease(session, target, later, Failed())
    assert again is not None and again.id == job.id and again.lease_id != old
    with pytest.raises(Conflict):
        tool_jobs.heartbeat(session, target, job.id, old, later)


def test_rented_target_gets_no_tool_job(session: Session) -> None:
    rented = _target(session, ComputeKind.RENTED)
    _enqueue(session, ToolJobKind.QUICK_TRY, T0)
    assert tool_jobs.lease(session, rented, T0, Failed()) is None
