"""Schema experiment trên web (requirements.md Phase 5, Thay đổi contract)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from pydantic import BaseModel, ValidationError

from advertest_contracts.enums import DisplayMode, ExperimentStatus, RunStatus
from advertest_contracts.models import (
    ComputeTargetPublic,
    DatasetSummary,
    ErrorResponse,
    EstimateResponse,
    ExperimentClone,
    ExperimentCreate,
    ExperimentDetail,
    ExperimentSummary,
    FailureCaseView,
    RunView,
)

MOCKS = Path(__file__).resolve().parents[2] / "mocks"


def mock(schema: str, name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((MOCKS / schema / f"{name}.json").read_text())
    return data


def statuses(schema: str, model: type[BaseModel], field: str) -> set[Any]:
    return {
        getattr(model.model_validate_json(p.read_text()), field)
        for p in (MOCKS / schema).glob("*.json")
    }


# ---------------------------------------------------------------- độ phủ của mock (plan.md task 3)


def test_experiment_mocks_cover_every_status() -> None:
    assert statuses("experiment_summary", ExperimentSummary, "status") == set(ExperimentStatus)


def test_run_view_mocks_cover_every_status_and_partial() -> None:
    assert statuses("run_view", RunView, "status") == set(RunStatus)
    views = [RunView.model_validate_json(p.read_text()) for p in (MOCKS / "run_view").glob("*")]
    assert any(v.metrics is not None and v.metrics.partial for v in views)


def test_failure_case_view_mocks_cover_every_display_mode() -> None:
    assert statuses("failure_case_view", FailureCaseView, "display_mode") == set(DisplayMode)


def test_estimate_mocks_cover_full_missing_and_exceeding() -> None:
    estimates = [EstimateResponse.model_validate(mock("estimate_response", n))
                 for n in ("full", "missing_profile", "exceeds_limit", "incompatible")]  # fmt: skip
    full, missing, exceeds, incompatible = estimates
    assert full.total_seconds is not None and not full.missing_profiles
    assert missing.total_seconds is None and missing.missing_profiles
    assert exceeds.exceeds_limit
    assert all(run.skip_reason == "incompatible" for run in incompatible.runs)


def test_completed_detail_matches_its_run_views() -> None:
    detail = ExperimentDetail.model_validate(mock("experiment_detail", "completed"))
    runs = [
        RunView.model_validate_json(p.read_text())
        for p in (MOCKS / "run_view").glob("*.json")
        if RunView.model_validate_json(p.read_text()).experiment_id == detail.id
    ]
    counts = detail.run_counts.model_dump()
    assert sum(counts.values()) == len(runs)
    for status in RunStatus:
        assert counts[status.value] == sum(r.status == status for r in runs)


# ---------------------------------------------------------------- ExperimentCreate, clone


def test_experiment_create_name_is_optional_and_trimmed() -> None:
    body = mock("experiment_create", "fgsm_pgd")
    assert ExperimentCreate.model_validate(body).name is None
    assert ExperimentCreate.model_validate({**body, "name": "  Tên  "}).name == "Tên"
    with pytest.raises(ValidationError):
        ExperimentCreate.model_validate({**body, "name": "   "})


def test_clone_warning_must_reference_an_attack_in_config() -> None:
    data = mock("experiment_clone", "spec_updated")
    data["warnings"][0]["attack_spec_id"] = str(uuid4())
    with pytest.raises(ValidationError, match="warnings"):
        ExperimentClone.model_validate(data)


def test_clone_warning_version_must_increase() -> None:
    data = mock("experiment_clone", "spec_updated")
    data["warnings"][0]["to_version"] = 1
    with pytest.raises(ValidationError, match="to_version"):
        ExperimentClone.model_validate(data)


# ---------------------------------------------------------------- EstimateResponse


def test_skipped_run_has_zero_estimate() -> None:
    data = mock("estimate_response", "incompatible")
    data["runs"][0]["est_seconds"] = 10.0
    with pytest.raises(ValidationError, match="est_seconds = 0"):
        EstimateResponse.model_validate(data)


def test_total_is_null_iff_some_run_lacks_a_profile() -> None:
    data = mock("estimate_response", "missing_profile")
    data["total_seconds"] = 100.0
    with pytest.raises(ValidationError, match="total_seconds"):
        EstimateResponse.model_validate(data)
    full = mock("estimate_response", "full")
    full["total_seconds"] = None
    with pytest.raises(ValidationError, match="total_seconds"):
        EstimateResponse.model_validate(full)


def test_missing_profiles_lists_exactly_the_unestimated_attacks() -> None:
    data = mock("estimate_response", "missing_profile")
    data["missing_profiles"] = []
    with pytest.raises(ValidationError, match="missing_profiles"):
        EstimateResponse.model_validate(data)


def test_exceeds_limit_may_hold_while_some_profile_is_missing() -> None:
    # Review Group 0, phát hiện #1: phần ước lượng được đã vượt giới hạn thì vẫn cảnh báo.
    data = {**mock("estimate_response", "missing_profile"), "exceeds_limit": True}
    assert EstimateResponse.model_validate(data).exceeds_limit


def test_profile_and_estimate_are_null_together() -> None:
    data = mock("estimate_response", "full")
    data["runs"][0]["est_seconds"] = None
    with pytest.raises(ValidationError, match="cùng null"):
        EstimateResponse.model_validate(data)


# ---------------------------------------------------------------- ExperimentSummary, Detail


@pytest.mark.parametrize("status", ["draft", "queued", "running"])
def test_unfinished_experiment_has_no_finished_at(status: str) -> None:
    data = {**mock("experiment_summary", "completed"), "status": status}
    with pytest.raises(ValidationError, match="finished_at"):
        ExperimentSummary.model_validate(data)


def test_finished_experiment_requires_finished_at() -> None:
    data = {**mock("experiment_summary", "cancelled"), "finished_at": None}
    with pytest.raises(ValidationError, match="finished_at"):
        ExperimentSummary.model_validate(data)


def test_queue_position_only_when_queued() -> None:
    queued = {**mock("experiment_detail", "queued"), "queue_position": None}
    with pytest.raises(ValidationError, match="queue_position"):
        ExperimentDetail.model_validate(queued)
    running = {**mock("experiment_detail", "running"), "queue_position": 1}
    with pytest.raises(ValidationError, match="queue_position"):
        ExperimentDetail.model_validate(running)


def test_detail_limit_matches_config() -> None:
    data = mock("experiment_detail", "completed")
    data["limit"] = {"kind": "time", "value": "60"}
    with pytest.raises(ValidationError, match="limit"):
        ExperimentDetail.model_validate(data)


# ---------------------------------------------------------------- FailureCaseView


def test_hidden_case_has_no_url() -> None:
    data = mock("failure_case_view", "hidden_unanonymized")
    data["urls"]["clean_thumb"] = "/artifacts/abc"
    with pytest.raises(ValidationError, match="hidden_unanonymized"):
        FailureCaseView.model_validate(data)


def test_visible_case_requires_expiry() -> None:
    data = {**mock("failure_case_view", "dev_unblurred"), "urls_expire_at": None}
    with pytest.raises(ValidationError, match="urls_expire_at"):
        FailureCaseView.model_validate(data)


@pytest.mark.parametrize(
    "url", ["http://127.0.0.1:9000/artifacts/x", "/api/artifacts/x", "/artifacts/../x"]
)
def test_artifact_url_is_relative_to_api(url: str) -> None:
    data = mock("failure_case_view", "normal_full")
    data["urls"]["clean"] = url
    with pytest.raises(ValidationError):
        FailureCaseView.model_validate(data)


# ---------------------------------------------------------------- tài nguyên, lỗi


def test_compute_target_default_limit_within_max() -> None:
    data = {**mock("compute_target_public", "local_online"), "default_time_limit_s": 30000}
    with pytest.raises(ValidationError, match="max_time_limit_s"):
        ComputeTargetPublic.model_validate(data)


def test_dataset_versions_belong_to_dataset() -> None:
    data = mock("dataset_summary", "kitti_unanonymized")
    data["versions"][0]["dataset_id"] = str(uuid4())
    with pytest.raises(ValidationError, match="dataset_id"):
        DatasetSummary.model_validate(data)


def test_error_fields_are_omitted_when_absent() -> None:
    plain = ErrorResponse.model_validate(mock("error_response", "not_implemented"))
    assert plain.error.fields is None
    assert "fields" not in plain.model_dump(mode="json", exclude_none=True)["error"]
    detailed = ErrorResponse.model_validate(mock("error_response", "invalid_fields"))
    assert detailed.error.fields is not None
    assert [f.path for f in detailed.error.fields] == ["attacks.0.grid.levels", "limit.value"]
