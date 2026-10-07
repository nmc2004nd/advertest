"""Dừng sớm trong worker (validation.md Phase 6, mục Thứ tự và dừng sớm; plan task 16)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID

from advertest_contracts.enums import RunStatus
from advertest_contracts.models import MapPair, RunMetrics, RunSkipRequest, WorkerJobBundle
from advertest_worker.early_stop import RunLedger, skip_early_stop

MOCK = Path(__file__).resolve().parents[3] / "contracts/mocks/worker_job_bundle"


def _bundle(**grid: Any) -> WorkerJobBundle:
    data = json.loads((MOCK / "patch_resume_early_stop.json").read_text())
    for attack in data["config"]["attacks"]:
        attack["grid"].update(grid)
    return WorkerJobBundle.model_validate(data)


def _runs(bundle: WorkerJobBundle) -> dict[float, UUID]:
    """run_id của FGSM theo level (mock: 2 xong, 8 xong và sụp, 32 chờ)."""
    fgsm = bundle.config.attacks[0].attack_spec_id
    return {r.level: r.run_id for r in bundle.runs if r.attack_spec_id == fgsm}


def _metrics(attacked: float) -> RunMetrics:
    return RunMetrics(
        clean=MapPair(map50=0.5, map50_95=0.3),
        attacked=MapPair(map50=attacked, map50_95=attacked / 2),
        relative_drop=(0.5 - attacked) / 0.5,
        absolute_drop=0.5 - attacked,
        attack_success_rate=None,
    )


def test_resume_recomputes_early_stop_from_bundle_metrics() -> None:
    bundle = _bundle()
    runs = _runs(bundle)
    ledger = RunLedger(bundle)
    stop = ledger.decision(runs[32])
    assert stop is not None and stop.trigger_run_id == runs[8] and stop.trigger_level == 8
    assert ledger.decision(runs[2]) is None  # đã xong, không bỏ
    # Attack khác (patch) không bị ảnh hưởng.
    patch_runs = [r.run_id for r in bundle.runs if r.patch_key is not None]
    assert all(ledger.decision(run_id) is None for run_id in patch_runs)


def test_disabled_flag_runs_everything() -> None:
    bundle = _bundle(early_stop=False)
    assert RunLedger(bundle).decision(_runs(bundle)[32]) is None


def test_in_session_results_are_used() -> None:
    bundle = _bundle()
    runs = _runs(bundle)
    ledger = RunLedger(bundle)
    ledger.record(runs[8], RunStatus.COMPLETED, _metrics(0.3))  # không còn sụp
    assert ledger.decision(runs[32]) is None
    ledger.record(runs[2], RunStatus.COMPLETED, _metrics(0.01))  # sụp ở level 2
    stop = ledger.decision(runs[32])
    assert stop is not None and stop.trigger_run_id == runs[2]


class _Client:
    def __init__(self) -> None:
        self.skipped: list[tuple[UUID, RunSkipRequest]] = []

    def skip(self, run_id: UUID, body: RunSkipRequest) -> None:
        self.skipped.append((run_id, body))


def test_skip_reports_to_api_and_updates_ledger() -> None:
    bundle = _bundle()
    runs = _runs(bundle)
    client = _Client()
    ledger = RunLedger(bundle)
    assert skip_early_stop(client, ledger, UUID(int=7), runs[32], "fgsm", 32)
    ((run_id, body),) = client.skipped
    assert run_id == runs[32] and body.trigger_run_id == runs[8] and body.code == "early_stop"
    assert body.lease_id == UUID(int=7)
    assert ledger.status(runs[32]) == RunStatus.SKIPPED
    # Gọi lại: run đã bị bỏ, không gửi lần nữa.
    assert not skip_early_stop(client, ledger, UUID(int=7), runs[32], "fgsm", 32)
    assert len(client.skipped) == 1
