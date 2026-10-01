"""Contract Phase 7: tự tìm ngưỡng (requirements.md Phase 7, mục Data / Fields và các quyết định
chốt ở kickoff)."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from advertest_contracts.enums import EvalScope, SearchStage, SearchStatus
from advertest_contracts.hashing import sha256_of
from advertest_contracts.models import (
    AttackConfig,
    BundleRun,
    EstimateResponse,
    ExperimentConfig,
    ExperimentDetail,
    Manifest,
    RunResult,
    RunView,
    SearchConfig,
    SearchEstimate,
    SearchResult,
    TrajectoryPoint,
    WorkerJobBundle,
)

MOCKS = Path(__file__).resolve().parents[2] / "mocks"


def mock(schema: str, name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((MOCKS / schema / f"{name}.json").read_text())
    return data


def invalid(model: type[BaseModel], data: dict[str, Any], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        model.model_validate(data)


# ---------------------------------------------------------------- hash cũ không đổi


def test_old_hashes_unchanged_by_new_optional_fields() -> None:
    detail = mock("experiment_detail", "completed")
    config = ExperimentConfig.model_validate(detail["config"])
    assert sha256_of(config) == detail["config_sha256"]
    manifest = Manifest.model_validate(mock("manifest", "gpu_local"))
    dumped = manifest.model_dump(mode="json")["fingerprint_inputs"]
    assert "eval_image_ids_sha256" not in dumped
    assert sha256_of(dumped) == manifest.fingerprint


def test_grid_run_dump_has_no_search_fields() -> None:
    dumped = RunResult.model_validate(mock("run_result", "completed")).model_dump(mode="json")
    assert not {"scope", "search_order", "predictions_key"} & set(dumped)
    per_class = dumped["metrics"]["per_class"]
    assert all("attack_success_rate" not in m for m in per_class.values())


def test_subset_manifest_has_eval_image_ids() -> None:
    manifest = Manifest.model_validate(mock("manifest", "search_subset_run"))
    assert manifest.fingerprint_inputs.eval_image_ids_sha256 is not None


# ---------------------------------------------------------------- SearchConfig


def _search_config(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = mock("attack_config", "search")["search"]
    return {**data, **overrides}


def test_search_config_defaults() -> None:
    config = SearchConfig.model_validate(
        {"threshold_kind": "relative_drop", "threshold": 0.2, "lo": 0, "hi": 32, "tol": 0.125}
    )
    assert (config.coarse_n, config.subset_size, config.bootstrap_samples) == (4, 100, 200)
    assert config.class_filter is None


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"lo": 32}, "lo phải nhỏ hơn hi"),
        ({"tol": 32}, "tol phải nhỏ hơn"),
        ({"tol": 0}, "greater than 0"),
        ({"coarse_n": 2}, "greater than or equal to 3"),
        ({"coarse_n": 9}, "less than or equal to 8"),
        ({"subset_size": 1}, "greater than or equal to 2"),
        ({"threshold": 0}, "greater than 0"),
        ({"threshold": 1.2}, "less than or equal to 1"),
        ({"bootstrap_samples": 1001}, "less than or equal to 1000"),
        ({"bootstrap_samples": -1}, "greater than or equal to 0"),
        ({"class_filter": ["person"]}, "string"),
        ({"class_filter": ""}, "at least 1"),
    ],
)
def test_search_config_rejects(overrides: dict[str, Any], match: str) -> None:
    invalid(SearchConfig, _search_config(**overrides), match)


def test_subset_size_two_is_allowed() -> None:
    SearchConfig.model_validate(_search_config(subset_size=2))


def test_attack_config_search_mocks() -> None:
    for name in ("search", "search_class_asr"):
        AttackConfig.model_validate(mock("attack_config", name))


# ---------------------------------------------------------------- RunResult, BundleRun


def test_subset_run_requires_search_order() -> None:
    data = mock("run_result", "completed_search_subset")
    assert RunResult.model_validate(data).scope == EvalScope.SUBSET
    invalid(RunResult, {**data, "search_order": None}, "search_order")
    invalid(
        RunView,
        {**mock("run_view", "search_pgd_0.5_subset_completed"), "search_order": None},
        "search_order",
    )


def test_predictions_key_inside_run_prefix() -> None:
    data = mock("run_result", "completed_search_subset")
    invalid(RunResult, {**data, "predictions_key": "runs/other/predictions.json"}, "runs/<run_id>")


def test_bundle_run_subset_requires_order() -> None:
    run = mock("worker_job_bundle", "search_resume_coarse")["runs"][-1]
    assert BundleRun.model_validate(run).scope == EvalScope.SUBSET
    invalid(BundleRun, {**run, "search_order": None}, "search_order")


# ---------------------------------------------------------------- TrajectoryPoint, SearchResult


def test_trajectory_point_rules() -> None:
    synthetic = {
        "order": 0,
        "level": 0,
        "scope": "subset",
        "drop": 0.0,
        "synthetic": True,
        "run_id": None,
    }
    TrajectoryPoint.model_validate(synthetic)
    invalid(TrajectoryPoint, {**synthetic, "drop": 0.1}, "drop = 0")
    invalid(TrajectoryPoint, {**synthetic, "synthetic": False}, "run_id là null")
    real = mock("search_result", "found")["trajectory"][-1]
    invalid(TrajectoryPoint, {**real, "scope": "subset"}, "drop_ci chỉ có ở điểm toàn slice")
    invalid(TrajectoryPoint, {**real, "drop_ci": [0.3, 0.2]}, "thấp, cao")


def test_search_result_mocks_cover_statuses_and_interim() -> None:
    results = [
        SearchResult.model_validate_json(p.read_text())
        for p in (MOCKS / "search_result").glob("*.json")
    ]
    assert {r.status for r in results} - {None} == set(SearchStatus)
    interim = [r for r in results if r.status is None]
    assert interim and all(r.stage != SearchStage.DONE for r in interim)
    scopes = {p.scope for r in results for p in r.trajectory}
    assert scopes == set(EvalScope)
    assert any(p.synthetic for r in results for p in r.trajectory)


def test_non_monotonic_keeps_breaking_point() -> None:
    data = mock("search_result", "non_monotonic")
    assert SearchResult.model_validate(data).breaking_point == data["bracket"][1]
    invalid(SearchResult, {**data, "breaking_point": None}, "found hoặc non_monotonic")


@pytest.mark.parametrize(
    ("name", "overrides", "match"),
    [
        ("found", {"breaking_point": 0.4}, "bằng bracket"),
        ("found", {"stage": "confirm"}, "stage khác done"),
        ("running_bisect_subset", {"status": "found"}, "stage khác done"),
        ("failed", {"message": None}, "message có khi"),
        ("found", {"message": "x"}, "message có khi"),
        ("found", {"metric_kind": "asr"}, "metric_kind"),
        ("stopped_limit", {"metric_kind": "map50"}, "metric_kind"),
        ("found", {"points_used": 3}, "points_used phải bằng"),
        ("found", {"max_points": 5}, "không được vượt max_points"),
    ],
)
def test_search_result_rejects(name: str, overrides: dict[str, Any], match: str) -> None:
    invalid(SearchResult, {**mock("search_result", name), **overrides}, match)


def test_search_result_trajectory_order_and_unique_runs() -> None:
    data = mock("search_result", "found")
    shuffled = copy.deepcopy(data)
    shuffled["trajectory"][1]["order"] = 5
    invalid(SearchResult, shuffled, "liên tục")
    duplicated = copy.deepcopy(data)
    duplicated["trajectory"][2]["run_id"] = duplicated["trajectory"][1]["run_id"]
    invalid(SearchResult, duplicated, "mỗi run")


# ---------------------------------------------------------------- EstimateResponse


def test_search_estimate_sum() -> None:
    row = mock("estimate_response", "search_pgd_fog")["searches"][0]
    invalid(SearchEstimate, {**row, "max_points": row["max_points"] + 1}, "max_subset_points")


def test_estimate_search_rules() -> None:
    data = mock("estimate_response", "search_pgd_fog")
    estimate = EstimateResponse.model_validate(data)
    assert estimate.max_total_seconds is not None and estimate.total_seconds is not None
    assert estimate.max_total_seconds > estimate.total_seconds
    only = EstimateResponse.model_validate(mock("estimate_response", "search_only"))
    assert only.runs == [] and only.total_seconds == 0
    invalid(EstimateResponse, {**data, "runs": [], "searches": []}, "ít nhất một")
    invalid(EstimateResponse, {**data, "max_total_seconds": None}, "max_total_seconds")
    missing = mock("estimate_response", "search_missing_profile")
    assert EstimateResponse.model_validate(missing).max_total_seconds is None
    invalid(EstimateResponse, {**missing, "missing_profiles": []}, "missing_profiles")
    invalid(EstimateResponse, {**data, "searches": [data["searches"][0]] * 2}, "không được trùng")
    old = mock("estimate_response", "full")
    invalid(EstimateResponse, {**old, "max_exceeds_limit": True}, "chỉ true khi")
    invalid(EstimateResponse, {**old, "max_total_seconds": 1.0}, "max_total_seconds")


# ---------------------------------------------------------------- ExperimentDetail, bundle


def test_experiment_detail_search_results() -> None:
    data = mock("experiment_detail", "search_completed")
    detail = ExperimentDetail.model_validate(data)
    assert detail.config_sha256 == sha256_of(detail.config)
    assert {r.attack_spec_id for r in detail.search_results} <= {
        a.attack_spec_id for a in detail.config.attacks if a.mode == "search"
    }
    ExperimentDetail.model_validate(mock("experiment_detail", "search_running"))
    search_attack = data["search_results"][0]["attack_spec_id"]
    pgd_entry = {**data["attack_ranking"][0], "attack_spec_id": search_attack}
    invalid(ExperimentDetail, {**data, "attack_ranking": [pgd_entry]}, "quét lưới")
    twice = [data["search_results"][0]] * 2
    invalid(ExperimentDetail, {**data, "search_results": twice}, "tối đa một")
    grid_attack = data["attack_ranking"][0]["attack_spec_id"]
    stray = {**data["search_results"][0], "attack_spec_id": grid_attack}
    invalid(ExperimentDetail, {**data, "search_results": [stray]}, "tối đa một")


def test_bundle_search_rules() -> None:
    data = mock("worker_job_bundle", "search_resume_coarse")
    WorkerJobBundle.model_validate(data)
    grid_only = mock("worker_job_bundle", "resume_after_lease_expiry")
    invalid(WorkerJobBundle, {**grid_only, "runs": []}, "runs chỉ rỗng")
    runs = copy.deepcopy(data["runs"])
    runs[0]["search_order"] = 0
    invalid(WorkerJobBundle, {**data, "runs": runs}, "search_order có khi")
    invalid(WorkerJobBundle, {**data, "search_results": data["search_results"] * 2}, "tối đa một")
