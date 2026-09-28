"""Schema của API nội bộ worker (Phase 3)."""

import copy
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from advertest_contracts.models import (
    ArtifactUrlRequest,
    BundleRun,
    CostProfile,
    ProgressReport,
    RunCompletion,
    RunStartRequest,
    RunStartResponse,
    WorkerDirective,
    WorkerJobBundle,
)

MOCKS = Path(__file__).resolve().parents[2] / "mocks"


def _mock(path: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((MOCKS / path).read_text())
    return data


def _bundle() -> dict[str, Any]:
    return _mock("worker_job_bundle/resume_after_lease_expiry.json")


def test_bundle_mock_valid() -> None:
    bundle = WorkerJobBundle.model_validate(_bundle())
    assert [r.status for r in bundle.runs] == ["completed", "running", "queued"]
    assert bundle.runs[1].checkpoint is not None


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (lambda d: d["config"].update(model_version_id=str(uuid4())), "model_card.id"),
        (lambda d: d["config"].update(slice_id=str(uuid4())), "slice.id"),
        (lambda d: d["config"].update(class_mapping_id=str(uuid4())), "class_mapping.id"),
        (lambda d: d["attack_specs"].pop(), "attack_specs"),
        (lambda d: d["runs"][2].update(attack_spec_id=str(uuid4())), "attack_spec_id"),
        (lambda d: d["runs"][2].update(run_id=d["runs"][0]["run_id"]), "run_id"),
        (lambda d: d["downloads"]["images"].popitem(), "downloads.images"),
        (lambda d: d["limit"].update(value="60"), "limit"),
        (lambda d: d["cost_profiles"][0].update(compute_target_id=str(uuid4())), "cost_profiles"),
        (lambda d: d["runs"][2].update(checkpoint=d["runs"][1]["checkpoint"]), "checkpoint"),
        (lambda d: d["runs"][2].update(images_done=6), "images_done"),
        (lambda d: d["downloads"].update(weights="file:///etc/passwd"), None),
    ],
)
def test_bundle_rejects_inconsistent(mutate: Any, match: str | None) -> None:
    data = copy.deepcopy(_bundle())
    mutate(data)
    with pytest.raises(ValidationError, match=match):
        WorkerJobBundle.model_validate(data)


def test_bundle_run_needs_positive_total() -> None:
    run = _bundle()["runs"][2]
    with pytest.raises(ValidationError):
        BundleRun.model_validate({**run, "images_total": 0})


@pytest.mark.parametrize(
    "key",
    [
        "runs/x/candidates/000057/clean.png",
        "runs/x/checkpoints/12.json",
        "runs/x/cases/a-b_c/clean_thumb.webp",
    ],
)
def test_object_key_accepts(key: str) -> None:
    ArtifactUrlRequest.model_validate({"lease_id": str(uuid4()), "key": key, "method": "PUT"})


@pytest.mark.parametrize(
    "key",
    [
        "",
        "/runs/x/a.png",
        "runs/x/",
        "runs//x",
        "runs/x/../y/a.png",
        "runs/./a.png",
        "../a.png",
        "runs/x/.hidden",
        "runs/x/a b.png",
        "runs\\x\\a.png",
    ],
)
def test_object_key_rejects(key: str) -> None:
    with pytest.raises(ValidationError):
        ArtifactUrlRequest.model_validate({"lease_id": str(uuid4()), "key": key, "method": "PUT"})


def test_artifact_url_request_methods() -> None:
    base = _mock("artifact_url_request/put_candidate.json")
    for method in ("PUT", "GET", "DELETE"):
        ArtifactUrlRequest.model_validate({**base, "method": method})
    with pytest.raises(ValidationError):
        ArtifactUrlRequest.model_validate({**base, "method": "POST"})


def test_run_start_request_checks_fingerprint() -> None:
    data = _mock("run_start_request/gpu_local.json")
    RunStartRequest.model_validate(data)
    with pytest.raises(ValidationError, match="fingerprint"):
        RunStartRequest.model_validate({**data, "fingerprint": "0" * 64})


def test_run_start_response_cache_fields() -> None:
    skip = _mock("run_start_response/skip_cached.json")
    RunStartResponse.model_validate(skip)
    with pytest.raises(ValidationError, match="skip_cached"):
        RunStartResponse.model_validate({**skip, "action": "run"})
    with pytest.raises(ValidationError, match="skip_cached"):
        RunStartResponse.model_validate({**skip, "cached_result": None})
    with pytest.raises(ValidationError, match="cached_result"):
        RunStartResponse.model_validate({**skip, "cached_from_run_id": str(uuid4())})
    failed = _mock("run_result/failed.json")
    with pytest.raises(ValidationError, match="cached_result"):
        RunStartResponse.model_validate(
            {
                "action": "skip_cached",
                "cached_from_run_id": failed["run_id"],
                "cached_result": failed,
            }
        )


def test_progress_report_rejects_negative_and_bad_key() -> None:
    data = _mock("progress_report/after_batch_0.json")
    ProgressReport.model_validate(data)
    with pytest.raises(ValidationError):
        ProgressReport.model_validate({**data, "processing_seconds_delta": -1})
    with pytest.raises(ValidationError):
        ProgressReport.model_validate({**data, "checkpoint_key": "../x.json"})


def test_worker_directive() -> None:
    WorkerDirective.model_validate({"action": "continue", "remaining_seconds": None})
    with pytest.raises(ValidationError):
        WorkerDirective.model_validate({"action": "pause", "remaining_seconds": 1})
    with pytest.raises(ValidationError):
        WorkerDirective.model_validate({"action": "continue", "remaining_seconds": -1})


def test_cost_profile() -> None:
    data = _mock("cost_profile/gpu_local_pgd.json")
    CostProfile.model_validate(data)
    with pytest.raises(ValidationError, match="compute_target_id"):
        CostProfile.model_validate({**data, "compute_target_id": str(uuid4())})
    for field, value in [("sec_per_image", 0), ("batch_size", 0), ("peak_vram_mb", -1)]:
        with pytest.raises(ValidationError):
            CostProfile.model_validate({**data, field: value})
    with pytest.raises(ValidationError, match="UTC"):
        CostProfile.model_validate({**data, "measured_at": "2026-09-29T15:00:00+07:00"})


def _completion() -> dict[str, Any]:
    return _mock("run_completion/completed_one_case.json")


def test_run_completion_mocks_valid() -> None:
    done = RunCompletion.model_validate(_completion())
    assert done.failure_cases[0].artifacts.clean_thumb is not None
    RunCompletion.model_validate(_mock("run_completion/failed.json"))


def test_run_completion_ids_must_match_cases() -> None:
    data = copy.deepcopy(_completion())
    data["run_result"]["failure_case_ids"] = [str(uuid4())]
    with pytest.raises(ValidationError, match="failure_case_ids"):
        RunCompletion.model_validate(data)
    data = copy.deepcopy(_completion())
    data["failure_cases"] = []
    with pytest.raises(ValidationError, match="failure_case_ids"):
        RunCompletion.model_validate(data)


def test_run_completion_case_must_belong_to_run() -> None:
    data = copy.deepcopy(_completion())
    data["run_result"]["fingerprint"] = "f" * 64
    with pytest.raises(ValidationError, match="fingerprint"):
        RunCompletion.model_validate(data)


def test_run_completion_rejects_cached_result() -> None:
    cached = _mock("run_result/skipped_cached_phase3.json")
    with pytest.raises(ValidationError, match="cached"):
        RunCompletion.model_validate(
            {
                "lease_id": str(uuid4()),
                "run_result": {**cached, "failure_case_ids": []},
                "failure_cases": [],
            }
        )
