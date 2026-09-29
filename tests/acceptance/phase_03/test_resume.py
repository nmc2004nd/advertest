"""Chạy tiếp sau gián đoạn (validation.md Phase 3, test_resume.py).

Lần chạy liền mạch và lần bị gián đoạn dùng GIT_COMMIT khác nhau: fingerprint khác (không trúng
cache), mã và kết quả như nhau.
"""

from __future__ import annotations

import uuid
from collections import Counter
from typing import Any
from uuid import UUID

import pytest

from advertest_contracts.enums import ExperimentStatus, RunStatus
from backend.app.storage import Buckets

from .conftest import Crash, Harness, artifact_keys, batch_counter, crash_after

pytestmark = pytest.mark.db
ATTACKS = {"fgsm": [4.0]}
Result = tuple[dict[str, Any], list[tuple[str, float]]]


def _run(harness: Harness, commit: str, monkeypatch: pytest.MonkeyPatch) -> tuple[str, str, UUID]:
    monkeypatch.setenv("GIT_COMMIT", commit)
    name, token = harness.target()
    harness.profile(name, token, sec=0.01, batch=1, attacks=list(ATTACKS))
    return name, token, harness.submit(name, harness.world.config(ATTACKS, seed=5))


def _result(
    harness: Harness, experiment_id: UUID
) -> tuple[dict[str, Any], list[tuple[str, float]]]:
    experiment, runs = harness.state(experiment_id)
    assert experiment.status == ExperimentStatus.COMPLETED
    assert runs[0].status == RunStatus.COMPLETED and runs[0].metrics is not None
    cases = [(c.image_id, c.severity_score) for c in harness.cases(runs[0].id)]
    return runs[0].metrics, cases


@pytest.fixture
def baseline(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> tuple[dict[str, Any], list[tuple[str, float]]]:
    # Commit riêng mỗi lần: lần chạy liền mạch của test trước không làm test này trúng cache.
    commit = (uuid.uuid4().hex + uuid.uuid4().hex)[:40]
    _, token, experiment_id = _run(harness, commit, monkeypatch)
    harness.work(token, experiment_id)
    return _result(harness, experiment_id)


def _assert_same(result: Result, baseline: Result) -> None:
    metrics, cases = result
    base_metrics, base_cases = baseline
    assert metrics["attacked"]["map50"] == pytest.approx(
        base_metrics["attacked"]["map50"], abs=0.005
    )
    assert metrics["clean"]["map50"] == pytest.approx(base_metrics["clean"]["map50"], abs=0.005)
    assert metrics["attack_success_rate"] == pytest.approx(
        base_metrics["attack_success_rate"], abs=0.01
    )
    assert cases == base_cases


def test_resume_after_worker_dies(
    harness: Harness, buckets: Buckets, baseline: Result, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, token, experiment_id = _run(harness, "6" * 40, monkeypatch)
    seen: list[tuple[UUID, str]] = []
    with pytest.raises(Crash):
        harness.work(token, experiment_id, cache="a", on_batch=crash_after(2, seen))
    _, runs = harness.state(experiment_id)
    assert runs[0].status == RunStatus.RUNNING and runs[0].images_done == 2

    harness.clock.advance(61)  # lease hết hạn
    more, hook = batch_counter()
    harness.work(token, experiment_id, cache="b", on_batch=hook)  # worker khác (cache khác)
    counts = Counter(seen + more)
    assert set(counts) == {(runs[0].id, i) for i in harness.world.image_ids}
    assert set(counts.values()) == {1}  # mỗi ảnh đúng một lần
    assert len(more) == len(harness.world.image_ids) - 2  # tiếp tục từ batch k+1
    _assert_same(_result(harness, experiment_id), baseline)
    assert artifact_keys(buckets, runs[0].id, "candidates") == []


def test_two_interruptions_give_same_result(
    harness: Harness, baseline: Result, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, token, experiment_id = _run(harness, "7" * 40, monkeypatch)
    seen: list[tuple[UUID, str]] = []
    with pytest.raises(Crash):
        harness.work(token, experiment_id, cache="a", on_batch=crash_after(1, seen))
    harness.clock.advance(61)
    with pytest.raises(Crash):
        harness.work(token, experiment_id, cache="b", on_batch=crash_after(2, seen))
    harness.clock.advance(61)
    more, hook = batch_counter()
    harness.work(token, experiment_id, cache="c", on_batch=hook)
    counts = Counter(seen + more)
    assert len(counts) == len(harness.world.image_ids) and set(counts.values()) == {1}
    _assert_same(_result(harness, experiment_id), baseline)
