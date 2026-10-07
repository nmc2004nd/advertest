"""Luồng patch trong `JobRunner` (review Group 3 #1, #2)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest

from advertest_contracts.enums import RunStatus
from advertest_contracts.models import (
    Environment,
    Manifest,
    RunCompletion,
    WorkerJobBundle,
)
from advertest_worker.early_stop import RunLedger
from advertest_worker.job import JobRunner, _Finisher
from ml_core.runner.manifest import ManifestBuilder

MOCKS = Path(__file__).resolve().parents[3] / "contracts/mocks"


def _bundle() -> WorkerJobBundle:
    data = json.loads((MOCKS / "worker_job_bundle/patch_resume_early_stop.json").read_text())
    return WorkerJobBundle.model_validate(data)


def _patch_run(bundle: WorkerJobBundle, level: float) -> Any:
    return next(r for r in bundle.runs if r.patch_key is not None and r.level == level)


def test_bundle_patch_key_mismatch_fails_before_training() -> None:
    bundle = _bundle()
    run = _patch_run(bundle, 0.1)
    # Seed của run lệch với seed dùng để tính khóa patch trong bundle (lỗi phía backend).
    tampered = bundle.model_copy(
        update={"runs": [r.model_copy(update={"seed": 9}) if r is run else r for r in bundle.runs]}
    )
    spec = next(s for s in bundle.attack_specs if s.requires_training)
    runner = JobRunner.__new__(JobRunner)
    runner.cache = cast(Any, None)  # không được chạm tới cache (không tải ảnh huấn luyện)
    job = cast(Any, SimpleNamespace(bundle=tampered, runs={r.run_id: r for r in tampered.runs}))
    with pytest.raises(ValueError, match="không khớp"):
        runner._patch_perturbation(job, run.run_id, spec, cast(Any, None))


class _Client:
    def __init__(self) -> None:
        self.completed: list[RunCompletion] = []

    def complete(self, run_id: UUID, body: RunCompletion) -> None:
        self.completed.append(body)


class _Store:
    def put(self, key: str, data: bytes) -> None:
        pass


def test_training_seconds_added_to_gpu_seconds() -> None:
    bundle = _bundle()
    run = _patch_run(bundle, 0.1)
    spec = next(s for s in bundle.attack_specs if s.requires_training)
    manifest = Manifest.model_validate_json((MOCKS / "manifest/patch_run.json").read_text())
    client = _Client()
    runner = cast(
        Any, SimpleNamespace(client=client, clock=lambda: datetime(2026, 10, 1, tzinfo=UTC))
    )
    environment = Environment(
        compute_target_id=None, gpu_model=None, cuda_version=None, driver_version=None
    )
    job = cast(
        Any,
        SimpleNamespace(
            bundle=bundle,
            lease=SimpleNamespace(lease_id=UUID(int=5)),
            environment=environment,
            ledger=RunLedger(bundle),
            outcomes={},
            manifests=ManifestBuilder(lambda: environment, runner.clock),
        ),
    )
    finish = _Finisher(
        runner,
        job,
        run,
        spec,
        manifest.fingerprint,
        manifest.fingerprint_inputs,
        cast(Any, _Store()),
        f"runs/{run.run_id}",
        images_total=run.images_total,
    )
    finish.extra_seconds = 12.5
    finish.stopped(None)  # dừng giữa lúc train: chưa có executor
    (completion,) = client.completed
    assert completion.run_result.status == RunStatus.STOPPED_LIMIT
    assert completion.run_result.gpu_seconds == 12.5
