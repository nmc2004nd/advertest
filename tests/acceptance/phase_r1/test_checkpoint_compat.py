"""Checkpoint do code trước R1 ghi (validation.md Phase R1, `### Checkpoint`), marker `db`.

Fixture `phase_r1_checkpoint.json` do người duyệt ghi trên code trước refactor (`6861ca8`): một run
PGD L∞ eps 4 (batch 1) trên world Phase 6, worker chết sau batch 0. Test trên code hiện tại:
1. chạy liền mạch cùng cấu hình (commit khác, không trúng cache) làm mốc;
2. chạy với commit ghim, worker chết sau batch 0; thay checkpoint mà API đang trỏ tới bằng nội dung
   của fixture (cùng fingerprint);
3. worker khác chạy tiếp từ batch kế tiếp: không xử lý lại ảnh của batch 0, kết quả cuối khớp mốc
   (metric trong sai số, failure case như nhau).

Ghi fixture: `ADVERTEST_RECORD_GOLDEN=1` (chỉ người duyệt, chỉ trên code chưa refactor); test ghi
file rồi fail có chủ đích.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from advertest_contracts.enums import RunStatus
from attacks.registry import get_spec, load_catalog
from backend.app.db import models as m

from .conftest import P5, P6
from .golden import ASR_TOL, GOLDEN_DIR, MAP_TOL, RECORD_ENV, SEVERITY_TOL

pytestmark = pytest.mark.db

FIXTURE = GOLDEN_DIR / "phase_r1_checkpoint.json"
ATTACK = "pgd_linf"
LEVEL = 4.0
# Khác `COMMIT` của golden worker: cùng phiên `make test-db`, run PGD eps 4 của golden không được
# làm run ở đây trúng cache.
CHECKPOINT_COMMIT = "3" * 40
BASELINE_COMMIT = "4" * 40


class Crash(BaseException):
    """Worker chết đột ngột (kill -9): không gửi gì thêm."""


def _crash_after_first(seen: list[str]) -> Callable[[UUID, Sequence[str]], None]:
    def hook(_run_id: UUID, ids: Sequence[str]) -> None:
        seen.extend(ids)
        raise Crash

    return hook


def _submit(api: Any, commit: str, monkeypatch: pytest.MonkeyPatch) -> tuple[Any, str]:
    monkeypatch.setenv("GIT_COMMIT", commit)
    target = api.target()
    P6.profile(api, target, {get_spec(load_catalog(), name=ATTACK).id: 0.05}, batch=1)
    _, _, client = api.user("engineer")
    body = api.body(target, [P5.attack(ATTACK, [LEVEL])])
    created = P5.ok(P5.post(client, "/experiments", body)).json()
    return target, str(created["id"])


def _run(engine: Engine, experiment_id: str) -> m.Run:
    with Session(engine, expire_on_commit=False) as session:
        (run,) = session.scalars(
            select(m.Run).where(m.Run.experiment_id == UUID(experiment_id))
        ).all()
        session.expunge(run)
        return run


def _result(engine: Engine, experiment_id: str) -> tuple[dict[str, Any], list[tuple[Any, ...]]]:
    run = _run(engine, experiment_id)
    assert run.status == RunStatus.COMPLETED and run.metrics is not None, run.status_reason
    with Session(engine) as session:
        cases = session.scalars(
            select(m.FailureCase).where(m.FailureCase.run_id == run.id).order_by(m.FailureCase.rank)
        ).all()
        rows = [
            (c.image_id, c.lost_objects, c.new_false_positives, c.severity_score) for c in cases
        ]
    return run.metrics, rows


def _assert_same(
    result: tuple[dict[str, Any], list[tuple[Any, ...]]],
    baseline: tuple[dict[str, Any], list[tuple[Any, ...]]],
) -> None:
    (metrics, cases), (base_metrics, base_cases) = result, baseline
    for part in ("clean", "attacked"):
        for key in ("map50", "map50_95"):
            assert metrics[part][key] == pytest.approx(base_metrics[part][key], abs=MAP_TOL)
    assert metrics["attack_success_rate"] == pytest.approx(
        base_metrics["attack_success_rate"], abs=ASR_TOL
    )
    assert [c[:3] for c in cases] == [c[:3] for c in base_cases]
    for got, want in zip(cases, base_cases, strict=True):
        assert got[3] == pytest.approx(want[3], abs=SEVERITY_TOL)


@pytest.mark.usefixtures("pinned_threads")
def test_worker_resumes_from_pre_r1_checkpoint(
    app_engine: Engine, buckets: Any, cli_env: dict[str, str], world: Any, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    monkeypatch.delenv("DOCKER_IMAGE_DIGEST", raising=False)
    monkeypatch.delenv("DEV_ALLOW_UNBLURRED", raising=False)
    monkeypatch.setenv("TRUSTED_PROXIES", "testclient")
    api = P5.Api(app_engine, buckets, cli_env, world.base, tmp_path)
    recording = os.environ.get(RECORD_ENV) == "1"

    baseline = None
    if not recording:
        target, baseline_id = _submit(api, BASELINE_COMMIT, monkeypatch)
        api.work(target, baseline_id)
        baseline = _result(app_engine, baseline_id)

    target, experiment_id = _submit(api, CHECKPOINT_COMMIT, monkeypatch)
    first: list[str] = []
    with pytest.raises(Crash):
        api.work(target, experiment_id, on_batch=_crash_after_first(first))
    run = _run(app_engine, experiment_id)
    assert run.status == RunStatus.RUNNING and run.checkpoint_batch_index == 0
    assert run.checkpoint_key is not None and len(first) == 1

    if recording:
        recorded = {
            "fingerprint": run.fingerprint,
            "batch_index": run.checkpoint_batch_index,
            "image_ids": first,
            "checkpoint": json.loads(buckets.artifacts.get(run.checkpoint_key)),
        }
        text = json.dumps(recorded, indent=2, ensure_ascii=False, sort_keys=True)
        FIXTURE.write_text(text + "\n")
        pytest.fail(f"Đã ghi {FIXTURE.name}; chạy lại không có {RECORD_ENV} để xác nhận")

    assert FIXTURE.is_file(), f"Chưa có {FIXTURE.name}: người duyệt ghi bằng {RECORD_ENV}=1"
    fixture = json.loads(FIXTURE.read_text())
    assert run.fingerprint == fixture["fingerprint"], "cấu hình run khác lúc ghi fixture"
    assert first == fixture["image_ids"]
    # Checkpoint bất biến trong store: xóa rồi ghi nội dung do code trước R1 tạo ra.
    buckets.artifacts.delete(run.checkpoint_key)
    buckets.artifacts.put(run.checkpoint_key, json.dumps(fixture["checkpoint"]).encode())

    api.clock.advance(61)  # lease của worker đã chết hết hạn
    rest: list[str] = []
    api.work(target, experiment_id, on_batch=lambda _run_id, ids: rest.extend(ids))
    assert not set(first) & set(rest), "chạy lại ảnh của batch 0"
    assert sorted(first + rest) == sorted(world.base.image_ids)
    assert baseline is not None
    _assert_same(_result(app_engine, experiment_id), baseline)
