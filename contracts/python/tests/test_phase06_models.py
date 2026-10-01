"""Contract Phase 6: patch, dừng sớm, xếp hạng, làm mờ (requirements.md Phase 6, mục Contract và
"Chi tiết chốt ở Group 0")."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from pydantic import BaseModel, ValidationError

from advertest_contracts.enums import RunPhase, SkipReason
from advertest_contracts.hashing import sha256_of
from advertest_contracts.ids import content_id
from advertest_contracts.models import (
    AttackConfig,
    AttackRankingEntry,
    AttackSpec,
    AttackSpecBody,
    BundlePatch,
    EstimateRun,
    ExperimentConfig,
    ExperimentDetail,
    FailureCaseView,
    GridConfig,
    Manifest,
    PatchArtifact,
    ProgressReport,
    RunView,
    StatusReason,
    WorkerJobBundle,
    compute_spec_sha256,
)
from advertest_contracts.registry import SCHEMAS

MOCKS = Path(__file__).resolve().parents[2] / "mocks"
SEEDS = Path(__file__).resolve().parents[2] / "seeds" / "attack_specs.json"

# Hash của spec Phase 2 trước khi thêm trường Phase 6 (không được đổi).
OLD_SPEC_HASHES = {
    "fgsm": "a6d81b6643af13e1d2f7983ce51340f54c26629304f1fdd98b954c236c1e735f",
    "pgd_linf": "68fe8f72f176fe27981eadfe8b5e98bb36b8e85fc41c97b5702e2e149f52d72c",
    "pgd_l2": "fb54ce834934be1340423f2fb4283b37766e2c1ca74a8fceea9b762e64f7351e",
}


def mock(schema: str, name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((MOCKS / schema / f"{name}.json").read_text())
    return data


def invalid(model: type[BaseModel], data: dict[str, Any], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        model.model_validate(data)


# ---------------------------------------------------------------- hash cũ không đổi


def test_old_spec_hashes_unchanged() -> None:
    specs = {s["name"]: s for s in json.loads(SEEDS.read_text())}
    for name, expected in OLD_SPEC_HASHES.items():
        spec = AttackSpec.model_validate(specs[name])
        assert compute_spec_sha256(spec) == expected
        assert "requires_training" not in spec.model_dump(mode="json")
        assert "training" not in spec.model_dump(mode="json")


def test_old_config_sha256_and_fingerprint_unchanged() -> None:
    detail = mock("experiment_detail", "completed")
    config = ExperimentConfig.model_validate(detail["config"])
    assert sha256_of(config) == detail["config_sha256"]
    for attack in config.model_dump(mode="json")["attacks"]:
        assert "training_slice_id" not in attack
        assert "early_stop" not in attack["grid"]
    manifest = Manifest.model_validate(mock("manifest", "gpu_local"))
    assert "patch_key" not in manifest.model_dump(mode="json")["fingerprint_inputs"]
    assert manifest.fingerprint == sha256_of(manifest.fingerprint_inputs)


def test_default_values_are_omitted_and_other_values_kept() -> None:
    assert GridConfig(levels=[1]).model_dump(mode="json") == {"levels": [1.0]}
    assert GridConfig(levels=[1], early_stop=False).model_dump(mode="json") == {
        "levels": [1.0],
        "early_stop": False,
    }
    reason = StatusReason(code=SkipReason.CACHED, message="x")
    assert "trigger_run_id" not in reason.model_dump(mode="json")
    patch_manifest = Manifest.model_validate(mock("manifest", "patch_run"))
    assert patch_manifest.model_dump(mode="json")["fingerprint_inputs"]["patch_key"]
    assert patch_manifest.fingerprint == sha256_of(patch_manifest.fingerprint_inputs)


@pytest.mark.parametrize(
    ("schema", "fields"),
    [
        ("attack_spec", {"requires_training", "training"}),
        ("attack_config", {"training_slice_id"}),
    ],
)
def test_omittable_fields_not_required_and_without_default(schema: str, fields: set[str]) -> None:
    model = SCHEMAS[schema]
    for js in (
        model.model_json_schema(mode="validation"),
        model.model_json_schema(mode="serialization"),
    ):
        assert not fields & set(js.get("required", []))
        for name in fields:
            assert "default" not in js["properties"][name]


# ---------------------------------------------------------------- AttackSpec


def _spec_body(name: str) -> dict[str, Any]:
    spec = next(s for s in json.loads(SEEDS.read_text()) if s["name"] == name)
    return {k: v for k, v in spec.items() if k not in ("id", "spec_sha256")}


def test_attack_spec_training_rules() -> None:
    patch = _spec_body("adv_patch")
    invalid(AttackSpecBody, {**patch, "training": None}, "training có khi và chỉ khi")
    invalid(AttackSpecBody, {**patch, "requires_training": False}, "training có khi và chỉ khi")
    invalid(AttackSpecBody, {**patch, "requires_gradients": False}, "attack cần gradient")
    fog = _spec_body("fog")
    invalid(
        AttackSpecBody,
        {**fog, "requires_training": True, "training": patch["training"]},
        "attack cần gradient",
    )
    fgsm = _spec_body("fgsm")
    invalid(AttackSpecBody, {**fgsm, "access": "not_applicable"}, "not_applicable")


# ---------------------------------------------------------------- dừng sớm


def test_status_reason_trigger_only_with_early_stop() -> None:
    invalid(StatusReason, {"code": "early_stop", "message": "x"}, "trigger_run_id")
    invalid(
        StatusReason,
        {"code": "cached", "message": "x", "trigger_run_id": str(uuid4())},
        "trigger_run_id",
    )


def test_run_view_early_stop_may_have_no_fingerprint() -> None:
    view = mock("run_view", "catalog_fgsm_16_early_stop")
    assert view["fingerprint"] is None and view["status_reason"]["trigger_run_id"]
    RunView.model_validate(view)
    cached = {**view, "status_reason": {"code": "cached", "message": "x"}}
    invalid(RunView, cached, "fingerprint chỉ null")


def test_run_view_phase_rules() -> None:
    training = mock("run_view", "patch_training_0.1_running")
    assert training["phase"] == RunPhase.TRAINING and training["training"]
    invalid(RunView, {**training, "training": None}, "training có khi và chỉ khi")
    evaluating = mock("run_view", "patch_evaluating_running")
    invalid(RunView, {**evaluating, "training": {"done": 1, "total": 2}}, "training có khi")
    completed = mock("run_view", "catalog_fgsm_8_completed")
    invalid(RunView, {**completed, "phase": "evaluating"}, "phase chỉ có khi status = running")
    invalid(RunView, {**training, "training": {"done": 3, "total": 2}}, "done")


# ---------------------------------------------------------------- patch


def test_patch_artifact_rules() -> None:
    artifact = mock("patch_artifact", "trained_0.25")
    invalid(PatchArtifact, {**artifact, "seed": 1}, "compute_patch_key")
    invalid(PatchArtifact, {**artifact, "png_key": "patches/other/patch.png"}, "patches/<key>/")
    history = artifact["objective_history"][:-1]
    invalid(PatchArtifact, {**artifact, "objective_history": history}, "iterations")


def test_bundle_patch_rules() -> None:
    bundle = mock("worker_job_bundle", "patch_resume_early_stop")
    done = next(p for p in bundle["patches"] if p["artifact"] is not None)
    pending = next(p for p in bundle["patches"] if p["artifact"] is None)
    key = done["key"]
    invalid(BundlePatch, {**done, "checkpoint_key": f"patches/{key}/c.npz"}, "checkpoint_key")
    invalid(BundlePatch, {**done, "area_ratio": 0.1}, "cùng key và area_ratio")
    invalid(BundlePatch, {**pending, "checkpoint_key": "patches/x/c.npz"}, "patches/<key>/")


def _bundle() -> dict[str, Any]:
    return copy.deepcopy(mock("worker_job_bundle", "patch_resume_early_stop"))


def test_bundle_training_slices_rules() -> None:
    WorkerJobBundle.model_validate(_bundle())

    missing = _bundle()
    missing["training_slices"] = []
    invalid(WorkerJobBundle, missing, "training_slices phải đúng")

    other_version = _bundle()
    other_version["training_slices"][0]["dataset_version_sha256"] = "0" * 64
    # slice_sha256 và id của slice huấn luyện được tính lại để chỉ lệch dataset version.
    ts = other_version["training_slices"][0]
    body = {k: ts[k] for k in ("dataset_version_sha256", "filter", "seed", "size", "image_ids")}
    ts["slice_sha256"] = sha256_of(body)
    ts["id"] = str(content_id(ts["slice_sha256"]))
    for attack in other_version["config"]["attacks"]:
        if "training_slice_id" in attack:
            attack["training_slice_id"] = ts["id"]
    for patch in other_version["patches"]:
        patch["training_slice_id"] = ts["id"]
    invalid(WorkerJobBundle, other_version, "cùng dataset version")

    no_images = _bundle()
    first = no_images["training_slices"][0]["image_ids"][0]
    del no_images["downloads"]["images"][first]
    invalid(WorkerJobBundle, no_images, "downloads.images")


def test_bundle_training_slice_must_not_overlap_evaluation() -> None:
    bundle = _bundle()
    ts = bundle["training_slices"][0]
    ids = sorted({*ts["image_ids"][:-1], bundle["slice"]["image_ids"][0]})
    ts["image_ids"] = ids
    ts["image_ids_sha256"] = sha256_of(ids)
    body = {k: ts[k] for k in ("dataset_version_sha256", "filter", "seed", "size", "image_ids")}
    ts["slice_sha256"] = sha256_of(body)
    ts["id"] = str(content_id(ts["slice_sha256"]))
    for attack in bundle["config"]["attacks"]:
        if "training_slice_id" in attack:
            attack["training_slice_id"] = ts["id"]
    for patch in bundle["patches"]:
        patch["training_slice_id"] = ts["id"]
    invalid(WorkerJobBundle, bundle, "không được giao")


def test_bundle_patches_match_runs() -> None:
    bundle = _bundle()
    bundle["patches"] = bundle["patches"][:1]
    invalid(WorkerJobBundle, bundle, "patches phải đúng các patch_key")
    duplicated = _bundle()
    duplicated["patches"].append(duplicated["patches"][0])
    invalid(WorkerJobBundle, duplicated, "không được trùng key")


# ---------------------------------------------------------------- tiến độ và ước lượng


def test_progress_report_phase_rules() -> None:
    training = mock("progress_report", "patch_training_iter_120")
    ProgressReport.model_validate(training)
    invalid(ProgressReport, {**training, "iterations_done": None}, "iterations_done")
    invalid(ProgressReport, {**training, "iterations_done": 201}, "không được lớn hơn")
    invalid(ProgressReport, {**training, "images_done": 3}, "images_done = 0")
    invalid(ProgressReport, {**training, "batch_index": 1}, "batch_index = 0")
    evaluating = mock("progress_report", "after_batch_0")
    invalid(ProgressReport, {**evaluating, "iterations_done": 1, "iterations_total": 2}, "phase")


def test_estimate_training_seconds_rules() -> None:
    run = mock("estimate_response", "patch_training")["runs"][0]
    assert run["training_seconds"] is not None
    EstimateRun.model_validate(run)
    skipped = {**run, "skip_reason": "incompatible", "est_seconds": 0}
    invalid(EstimateRun, skipped, "training_seconds chỉ có khi")
    missing = {**run, "sec_per_image": None, "est_seconds": None}
    invalid(EstimateRun, missing, "training_seconds chỉ có khi")


# ---------------------------------------------------------------- xếp hạng


def _entry(**changes: Any) -> dict[str, Any]:
    base = mock("experiment_detail", "full_catalog")["attack_ranking"][0]
    return {**base, **changes}


def test_ranking_entry_rules() -> None:
    AttackRankingEntry.model_validate(_entry())
    one_point = _entry(levels_evaluated=1, levels_early_stopped=0)
    invalid(AttackRankingEntry, one_point, "auc_drop là null")
    # Một level có metric cộng một level early_stop đủ 2 điểm.
    AttackRankingEntry.model_validate(_entry(levels_evaluated=1, levels_early_stopped=1))
    empty = _entry(levels_evaluated=0, levels_early_stopped=0, auc_drop=None)
    invalid(AttackRankingEntry, empty, "coverage")
    invalid(
        AttackRankingEntry,
        _entry(levels_evaluated=0, levels_early_stopped=2, auc_drop=None),
        "early_stop cần",
    )


def test_experiment_ranking_order_and_membership() -> None:
    detail = mock("experiment_detail", "full_catalog")
    ranking = detail["attack_ranking"]
    assert ranking[-1]["auc_drop"] is None and any(e["partial"] for e in ranking)
    assert any(e["levels_early_stopped"] for e in ranking)
    invalid(ExperimentDetail, {**detail, "attack_ranking": ranking[::-1]}, "giảm dần")
    invalid(
        ExperimentDetail,
        {**detail, "attack_ranking": [ranking[0], ranking[0]]},
        "không được trùng",
    )
    stranger = {**ranking[0], "attack_spec_id": str(uuid4())}
    invalid(ExperimentDetail, {**detail, "attack_ranking": [stranger]}, "attack của config")


# ---------------------------------------------------------------- làm mờ


def test_anonymized_case_mocks() -> None:
    for name, kind in (("anonymized_patch", "patch_location"), ("anonymized_fog", "difference")):
        view = FailureCaseView.model_validate(mock("failure_case_view", name))
        assert view.anonymization is not None and view.anonymization.applied
        assert view.anonymization.method == "rule_v1"
        assert view.perturbation_kind == kind
    old = FailureCaseView.model_validate(mock("failure_case_view", "normal_full"))
    assert old.anonymization is None and old.perturbation_kind == "amplified_noise"


def test_attack_config_patch_mock() -> None:
    config = AttackConfig.model_validate(mock("attack_config", "patch_no_early_stop"))
    assert config.training_slice_id is not None
    assert config.grid is not None and config.grid.early_stop is False


def test_run_view_param_max_matches_spec() -> None:
    """Đề xuất contract 003: `attack_spec.param_max` là `primary_param.max` của spec đã chạy."""
    seeds = {
        (spec["name"], spec["version"]): spec["primary_param"]["max"]
        for spec in json.loads(SEEDS.read_text())
    }
    views = [RunView.model_validate_json(p.read_text()) for p in (MOCKS / "run_view").glob("*")]
    assert views
    for view in views:
        spec = view.attack_spec
        assert spec.param_max == seeds[(spec.name, spec.version)], spec.name
    data = mock("run_view", "catalog_fog_1_completed")
    for bad in (0, -1):
        data["attack_spec"]["param_max"] = bad
        with pytest.raises(ValidationError):
            RunView.model_validate(data)
