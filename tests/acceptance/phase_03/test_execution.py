"""Chạy và kết quả (validation.md Phase 3, test_execution.py): worker thật, YOLOv8n thật, 5 ảnh
fixture, CPU."""

from __future__ import annotations

import json
from typing import Any

import numpy as np
import pytest

from advertest_contracts.enums import ExperimentStatus, RunStatus
from attacks.art_adapter import ArtPerturbation
from backend.app.storage import Buckets

from .conftest import Harness, batch_counter, crash_after

pytestmark = pytest.mark.db
DIGEST = "sha256:" + "d" * 64


def _metrics(harness: Harness, experiment_id: Any) -> dict[float, dict[str, Any]]:
    _, runs = harness.state(experiment_id)
    return {run.level: run.metrics for run in runs if run.metrics is not None}


def test_fixture_experiment_matches_phase2_golden_then_cache_skips(
    harness: Harness, golden: dict[str, Any]
) -> None:
    name, token = harness.target()
    config = harness.world.config({"fgsm": [4], "pgd_linf": [4]})
    experiment_id = harness.submit(name, config)
    harness.work(token, experiment_id)
    experiment, runs = harness.state(experiment_id)
    assert experiment.status == ExperimentStatus.COMPLETED
    assert [r.status for r in runs] == [RunStatus.COMPLETED, RunStatus.COMPLETED]
    tol = golden["tolerance"]
    expected = {(g["attack"], g["level"]): g for g in golden["runs"]}
    for run, attack in zip(runs, ("fgsm", "pgd_linf"), strict=True):
        assert run.metrics is not None
        assert run.metrics["clean"]["map50"] == pytest.approx(golden["clean_map50"], abs=tol)
        g = expected[(attack, 4)]
        assert run.metrics["attacked"]["map50"] == pytest.approx(g["attacked_map50"], abs=tol)
        assert run.metrics["attack_success_rate"] == pytest.approx(
            g["attack_success_rate"], abs=tol
        )

    # Gửi lại cùng cấu hình: bỏ qua do cache, attack không được gọi.
    again = harness.submit(name, config)
    seen, hook = batch_counter()
    harness.work(token, again, on_batch=hook)
    experiment2, runs2 = harness.state(again)
    assert experiment2.status == ExperimentStatus.COMPLETED
    assert seen == []
    for original, cached in zip(runs, runs2, strict=True):
        assert cached.status == RunStatus.SKIPPED
        assert cached.status_reason is not None and cached.status_reason["code"] == "cached"
        assert cached.cached_from_run_id == original.id
        assert cached.metrics == original.metrics


def test_model_without_gradients_is_skipped_incompatible(harness: Harness) -> None:
    name, token = harness.target()
    experiment_id = harness.submit(name, harness.world.config({"fgsm": [4]}, gradient=False))
    harness.work(token, experiment_id)
    experiment, runs = harness.state(experiment_id)
    assert experiment.status == ExperimentStatus.COMPLETED
    assert runs[0].status == RunStatus.SKIPPED
    assert runs[0].status_reason is not None and runs[0].status_reason["code"] == "incompatible"


def test_exception_in_one_run_fails_only_that_run(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = ArtPerturbation.apply

    def apply(self: ArtPerturbation, images: np.ndarray, *args: Any, **kwargs: Any) -> Any:
        level = args[1] if len(args) > 1 else kwargs["level"]
        if level == 8:
            raise RuntimeError("lỗi giả lập ở eps 8")
        return original(self, images, *args, **kwargs)

    monkeypatch.setattr(ArtPerturbation, "apply", apply)
    name, token = harness.target()
    harness.profile(name, token, sec=0.01, batch=5, attacks=["fgsm"])
    experiment_id = harness.submit(name, harness.world.config({"fgsm": [4, 8]}, seed=1))
    harness.work(token, experiment_id)
    experiment, runs = harness.state(experiment_id)
    assert experiment.status == ExperimentStatus.COMPLETED
    assert [r.status for r in runs] == [RunStatus.COMPLETED, RunStatus.FAILED]
    reason = runs[1].status_reason
    assert reason is not None and reason["code"] == "error" and "eps 8" in reason["message"]


def test_completion_for_run_not_running_is_rejected(harness: Harness) -> None:
    from .conftest import REPO

    name, token = harness.target()
    experiment_id = harness.submit(name, harness.world.config({"fgsm": [4]}))
    lease = harness.client(token).lease()
    assert lease is not None
    _, runs = harness.state(experiment_id)
    completion = json.loads((REPO / "contracts/mocks/run_completion/failed.json").read_text())
    completion["lease_id"] = str(lease.lease_id)
    response = harness.api.post(
        f"/internal/worker/runs/{runs[0].id}/complete",
        json=completion,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 409
    _, runs = harness.state(experiment_id)
    assert runs[0].status == RunStatus.QUEUED


def test_manifest_in_docker_environment(
    harness: Harness, buckets: Buckets, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Worker trong image Docker có GIT_COMMIT và DOCKER_IMAGE_DIGEST (docker/worker/up.sh); việc
    chạy thật trong container là manual check."""
    monkeypatch.setenv("GIT_COMMIT", "4" * 40)
    monkeypatch.setenv("DOCKER_IMAGE_DIGEST", DIGEST)
    name, token = harness.target()
    harness.profile(name, token, sec=0.01, batch=5, attacks=["fgsm"])
    experiment_id = harness.submit(name, harness.world.config({"fgsm": [4]}))
    harness.work(token, experiment_id)
    _, runs = harness.state(experiment_id)
    assert runs[0].manifest_uri is not None
    manifest = json.loads(
        buckets.artifacts.get(runs[0].manifest_uri.removeprefix("s3://artifacts/"))
    )
    inputs = manifest["fingerprint_inputs"]
    assert inputs["docker_image_digest"] == DIGEST and inputs["git_dirty"] is False
    assert inputs["git_commit"] == "4" * 40
    assert manifest["environment"]["compute_target_id"] is not None


def test_checkpoint_has_no_image_data(harness: Harness, buckets: Buckets) -> None:
    name, token = harness.target()
    harness.profile(name, token, sec=0.01, batch=1, attacks=["fgsm"])
    experiment_id = harness.submit(name, harness.world.config({"fgsm": [4]}, seed=2))
    from .conftest import Crash

    with pytest.raises(Crash):
        harness.work(token, experiment_id, on_batch=crash_after(2))
    _, runs = harness.state(experiment_id)
    assert runs[0].checkpoint_key is not None
    data = buckets.artifacts.get(runs[0].checkpoint_key)
    checkpoint = json.loads(data)
    assert len(checkpoint["done"]) == 2
    assert len(data) < 3 * 640 * 640  # nhỏ hơn nhiều so với một ảnh 640x640
    assert not {"image", "images", "clean", "adversarial"} & set(checkpoint)
