"""Vòng lặp `advertest-worker run`: lỗi của một job không làm worker thoát."""

from __future__ import annotations

from typing import Any, cast
from uuid import uuid4

import httpx
import pytest

from advertest_worker.cli import serve
from advertest_worker.client import WorkerClient
from advertest_worker.job import JobRunner


class Stop(Exception):
    pass


class FakeClient:
    def __init__(self, leases: list[Any]) -> None:
        self.leases = leases

    def lease(self) -> Any:
        item = self.leases.pop(0) if self.leases else None
        if isinstance(item, Exception):
            raise item
        return item


class FakeRunner:
    def __init__(self, fail_on: set[Any]) -> None:
        self.fail_on = fail_on
        self.ran: list[Any] = []

    def run_lease(self, lease: Any) -> None:
        self.ran.append(lease)
        if lease in self.fail_on:
            raise RuntimeError("bundle hỏng")


def _lease() -> Any:
    return type("Lease", (), {"experiment_id": uuid4()})()


def test_serve_survives_failing_job_and_api_errors(caplog: pytest.LogCaptureFixture) -> None:
    bad, good = _lease(), _lease()
    client = FakeClient([bad, httpx.ConnectError("API tạm tắt"), good])
    runner = FakeRunner(fail_on={bad})
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        if not client.leases:
            raise Stop

    with pytest.raises(Stop):
        serve(cast(WorkerClient, client), cast(JobRunner, runner), poll_interval_s=5.0, sleep=sleep)
    assert runner.ran == [bad, good]
    assert sleeps == [5.0, 5.0, 5.0]  # sau job lỗi, sau lỗi API, khi hết job
    assert "bundle hỏng" in caplog.text and "API tạm tắt" in caplog.text


def test_serve_once_returns_even_after_failure() -> None:
    bad = _lease()
    runner = FakeRunner(fail_on={bad})
    serve(
        cast(WorkerClient, FakeClient([bad])),
        cast(JobRunner, runner),
        once=True,
        poll_interval_s=5.0,
        sleep=lambda _s: None,
    )
    assert runner.ran == [bad]
