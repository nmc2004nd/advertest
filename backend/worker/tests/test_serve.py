"""Vòng lặp `advertest-worker run`: lỗi của một job không làm worker thoát."""

from __future__ import annotations

from typing import Any, cast
from uuid import uuid4

import httpx
import pytest

from advertest_worker.cli import serve, serve_tools
from advertest_worker.client import WorkerClient
from advertest_worker.job import JobRunner
from advertest_worker.tools import ToolRunner


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


# ---------------------------------------------------------------- Phase R2: `--tools`


class FakeToolRunner:
    def __init__(self, results: list[bool | Exception]) -> None:
        self.results = results
        self.calls = 0

    def run_next(self) -> bool:
        self.calls += 1
        item = self.results.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def test_serve_tools_survives_errors_and_sleeps_only_when_idle() -> None:
    runner = FakeToolRunner([True, RuntimeError("API lỗi"), True, False])
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        if not runner.results:
            raise Stop

    with pytest.raises(Stop):
        serve_tools(cast(ToolRunner, runner), poll_interval_s=5.0, sleep=sleep)
    assert runner.calls == 4
    assert sleeps == [5.0, 5.0]  # sau lỗi và khi hết job


def test_serve_tools_once() -> None:
    runner = FakeToolRunner([False])
    sleeps: list[float] = []
    serve_tools(cast(ToolRunner, runner), once=True, poll_interval_s=5.0, sleep=sleeps.append)
    assert runner.calls == 1 and sleeps == []


def test_cli_tools_flag_requires_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from typer.testing import CliRunner

    from advertest_worker.cli import app

    monkeypatch.delenv("API_URL", raising=False)
    result = CliRunner().invoke(app, ["--tools", "--once"])
    assert isinstance(result.exception, RuntimeError)
    assert "API_URL" in str(result.exception)
    assert "--tools" in CliRunner().invoke(app, []).output
