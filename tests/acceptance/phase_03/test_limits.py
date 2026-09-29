"""Giới hạn và hủy (validation.md Phase 3, test_limits.py)."""

from __future__ import annotations

import time
from collections.abc import Sequence
from itertools import count
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from advertest_contracts.enums import ExperimentStatus, RunStatus
from backend.app.db import models as m
from backend.app.services import experiments
from ml_core.runner import executor as executor_module

from .conftest import ADMIN, Crash, Harness, admin, crash_after

pytestmark = pytest.mark.db


def test_small_time_limit_gives_partial_result(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Mỗi batch "tốn" 90 giây xử lý; giới hạn 100 giây; ước lượng 20 giây/ảnh, batch 4: batch đầu
    # chạy (ước lượng 80), batch kế (ước lượng 20 > 10 giây còn lại) không chạy.
    ticks = count(0, 90)
    monkeypatch.setattr(executor_module, "time", SimpleNamespace(perf_counter=lambda: next(ticks)))
    name, token = harness.target()
    harness.profile(name, token, sec=20.0, batch=4, attacks=["fgsm"])
    experiment_id = harness.submit(name, harness.world.config({"fgsm": [4, 8]}, seed=11),
                                   time_limit=100)  # fmt: skip
    harness.work(token, experiment_id)
    experiment, runs = harness.state(experiment_id)
    assert experiment.status == ExperimentStatus.COMPLETED
    assert [r.status for r in runs] == [RunStatus.STOPPED_LIMIT, RunStatus.STOPPED_LIMIT]
    current, later = runs
    assert current.status_reason is not None and current.status_reason["code"] == "time"
    assert current.metrics is not None and current.metrics["partial"] is True
    assert current.images_done == 4 < current.images_total
    assert later.images_done == 0 and later.metrics is None
    assert later.status_reason is not None and later.status_reason["code"] == "time"


def test_time_while_worker_down_not_counted(harness: Harness) -> None:
    name, token = harness.target()
    harness.profile(name, token, sec=0.01, batch=1, attacks=["fgsm"])
    experiment_id = harness.submit(name, harness.world.config({"fgsm": [4]}, seed=12))
    with pytest.raises(Crash):
        harness.work(token, experiment_id, cache="a", on_batch=crash_after(2))
    used_before, _ = harness.state(experiment_id)
    harness.clock.advance(3600)  # worker tắt một giờ
    harness.work(token, experiment_id, cache="b")
    experiment, runs = harness.state(experiment_id)
    assert experiment.status == ExperimentStatus.COMPLETED
    # Chỉ thời gian xử lý các batch được cộng (vài giây trên CPU), không có giờ bị dừng.
    used = float(experiment.processing_seconds_used)
    # processing_seconds_used là Numeric(18, 6): mỗi lần cộng làm tròn 6 chữ số thập phân.
    assert used == pytest.approx(runs[0].gpu_seconds, abs=1e-3)
    assert float(used_before.processing_seconds_used) < used < 600


def test_cancel_stops_after_current_batch(harness: Harness) -> None:
    name, token = harness.target()
    harness.profile(name, token, sec=0.01, batch=1, attacks=["fgsm"])
    experiment_id = harness.submit(name, harness.world.config({"fgsm": [4, 8]}, seed=13))
    processed: list[str] = []

    def cancel_after_first(_run_id: UUID, ids: Sequence[str]) -> None:
        processed.extend(ids)
        if len(processed) == 1:
            admin(harness.cli_env, "experiment", "cancel", str(experiment_id), "--as", ADMIN)
            time.sleep(0.5)  # luồng heartbeat nhận chỉ thị cancel

    harness.work(token, experiment_id, on_batch=cancel_after_first, heartbeat=0.1)
    experiment, runs = harness.state(experiment_id)
    assert experiment.status == ExperimentStatus.CANCELLED
    assert [r.status for r in runs] == [RunStatus.CANCELLED, RunStatus.CANCELLED]
    assert processed == harness.world.image_ids[:1]  # dừng sau batch hiện tại
    with Session(harness.app_engine) as session:
        assert experiments.get(session, experiment_id).lease_id is None
        assert session.get_one(m.Experiment, experiment_id).status == "cancelled"
