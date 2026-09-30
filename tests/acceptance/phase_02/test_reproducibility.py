"""Nghiệm thu Phase 2, mục Fingerprint, manifest, cache (validation.md)."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from advertest_contracts.hashing import sha256_of
from advertest_contracts.ids import content_id
from advertest_contracts.models import (
    ClassMapping,
    ClassMappingBody,
    Manifest,
    RunResult,
    compute_mapping_sha256,
)
from attacks.art_adapter import ArtPerturbation
from attacks.registry import get_spec, load_catalog
from ml_core.data.mapping import save_mapping
from ml_core.models.wrapper import DEFAULT_INFERENCE_PARAMS
from ml_core.runner import env as env_module
from ml_core.runner import run as run_module
from ml_core.runner.config import LocalRunConfig
from ml_core.runner.fingerprint import build_fingerprint_inputs, fingerprint
from ml_core.runner.run import run_config

from .conftest import (
    COMMIT,
    REPEAT,
    Pipeline,
    Rerun,
    Sweep,
    attack_entry,
    run_cli,
    run_results,
    write_config,
)

MAP_TOL = 0.005
ASR_TOL = 0.01


def _manifest(pipeline: Pipeline, result: RunResult) -> Manifest:
    assert result.manifest_uri is not None
    return Manifest.model_validate_json(pipeline.store.get(result.manifest_uri))


def _run_cli(pipeline: Pipeline, tmp: Path, config: dict[str, Any], *flags: str) -> RunResult:
    path = write_config(tmp / "run.yaml", config)
    out = run_cli(pipeline.store_dir, "run", "--config", str(path), *flags)
    (result,) = run_results(out.stdout)
    return result


class Spy:
    """Factory đếm số lần dựng attack và ghi lại nhãn được đưa vào attack."""

    def __init__(self) -> None:
        self.calls = 0
        self.targets: list[Any] = []

    def __call__(self, spec: Any, estimator: Any) -> ArtPerturbation:
        self.calls += 1
        spy = self

        class Recording(ArtPerturbation):
            def apply(
                self, images: Any, targets: Any, level: float, seed: int, mask: Any = None
            ) -> Any:
                spy.targets.extend(targets)
                return super().apply(images, targets, level, seed, mask)

        return Recording(spec, estimator)


# ---------------------------------------------------------------- manifest và fingerprint


def test_every_run_has_valid_manifest(pipeline: Pipeline, sweep: Sweep) -> None:
    for result in sweep.results.values():
        manifest = _manifest(pipeline, result)
        assert manifest.run_id == result.run_id
        assert manifest.fingerprint == result.fingerprint == sha256_of(manifest.fingerprint_inputs)
        assert result.manifest_uri == f"runs/{result.fingerprint}/manifest.json"
        assert pipeline.store.exists(f"runs/{result.fingerprint}/result.json")


def test_fingerprint_changes_with_level_and_spec(sweep: Sweep) -> None:
    assert len({r.fingerprint for r in sweep.results.values()}) == len(sweep.results)


@pytest.mark.usefixtures("git_commit")
def test_fingerprint_changes_with_seed(pipeline: Pipeline, sweep: Sweep, tmp_path: Path) -> None:
    other = _run_cli(pipeline, tmp_path, pipeline.config([attack_entry("fgsm", [4], seed=1)]))
    assert other.fingerprint != sweep.results[("fgsm", 4.0)].fingerprint


@pytest.mark.usefixtures("git_commit")
def test_fingerprint_changes_with_mapping(pipeline: Pipeline, sweep: Sweep, tmp_path: Path) -> None:
    mapping = ClassMapping.model_validate(pipeline.mapping)
    body = ClassMappingBody(
        dataset_version_sha256=mapping.dataset_version_sha256,
        model_id=mapping.model_id,
        preset=None,
        classes=mapping.classes,
        difficulty=None,
    )
    sha = compute_mapping_sha256(body)
    other = ClassMapping(**body.model_dump(), id=content_id(sha), mapping_sha256=sha)
    save_mapping(pipeline.store, other)
    config = pipeline.config([attack_entry("fgsm", [4])], mapping_id=str(other.id))
    result = _run_cli(pipeline, tmp_path, config)
    assert result.fingerprint != sweep.results[("fgsm", 4.0)].fingerprint


def test_fingerprint_changes_with_inference_params(pipeline: Pipeline, sweep: Sweep) -> None:
    manifest = _manifest(pipeline, sweep.results[("fgsm", 4.0)])
    inputs = manifest.fingerprint_inputs
    loader = pipeline.loader()
    args: dict[str, Any] = {
        "spec": get_spec(load_catalog(), name="fgsm"),
        "level": 4.0,
        "seed": 0,
        "mapping": loader.mapping,
        "slice_spec": loader.slice,
        "weights_sha256": inputs.weights_sha256,
        "git_commit": inputs.git_commit,
        "git_dirty": inputs.git_dirty,
        "lib_versions": inputs.lib_versions,
        "docker_image_digest": inputs.docker_image_digest,
    }
    same = build_fingerprint_inputs(params=DEFAULT_INFERENCE_PARAMS, **args)
    assert fingerprint(same) == manifest.fingerprint
    changed = DEFAULT_INFERENCE_PARAMS.model_copy(update={"conf": 0.01})
    assert fingerprint(build_fingerprint_inputs(params=changed, **args)) != manifest.fingerprint


def test_batch_size_does_not_change_fingerprint(sweep: Sweep, batch1: Rerun) -> None:
    for key, result in batch1.results.items():
        assert result.fingerprint == sweep.results[key].fingerprint


@pytest.mark.usefixtures("git_commit")
def test_device_does_not_change_fingerprint(
    pipeline: Pipeline, sweep: Sweep, tmp_path: Path
) -> None:
    # device = null (mặc định: GPU nếu có) thay vì "cpu": cùng fingerprint nên được lấy từ cache.
    result = _run_cli(pipeline, tmp_path, pipeline.config([attack_entry("fgsm", [4])], device=None))
    assert result.fingerprint == sweep.results[("fgsm", 4.0)].fingerprint
    assert result.status == "skipped"


@pytest.fixture
def dirty_repo(sweep: Sweep, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Repo git tạm (có `.ai-log/`) thay cho repo thật khi xác định git commit."""
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)

    git("init", "-q")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "t")
    (repo / ".ai-log").mkdir()
    (repo / ".ai-log" / "session.jsonl").write_text("{}\n")
    (repo / "code.py").write_text("x = 1\n")
    git("add", ".")
    git("commit", "-q", "-m", "init")
    monkeypatch.delenv("GIT_COMMIT", raising=False)
    monkeypatch.setattr(env_module, "REPO_ROOT", repo)
    return repo


def test_uncommitted_change_sets_git_dirty(pipeline: Pipeline, dirty_repo: Path) -> None:
    (dirty_repo / "code.py").write_text("x = 2\n")
    config = LocalRunConfig.model_validate(pipeline.config([attack_entry("fgsm", [4])]))
    result = run_config(pipeline.store, config).outcomes[0].result
    assert _manifest(pipeline, result).fingerprint_inputs.git_dirty


def test_ai_log_change_is_not_dirty(pipeline: Pipeline, dirty_repo: Path) -> None:
    (dirty_repo / ".ai-log" / "session.jsonl").write_text('{"x": 1}\n')
    config = LocalRunConfig.model_validate(pipeline.config([attack_entry("fgsm", [4])]))
    result = run_config(pipeline.store, config).outcomes[0].result
    assert not _manifest(pipeline, result).fingerprint_inputs.git_dirty


# ---------------------------------------------------------------- cache và --force


@pytest.mark.usefixtures("git_commit")
def test_second_run_is_cached_and_does_not_attack(pipeline: Pipeline, sweep: Sweep) -> None:
    config = LocalRunConfig.model_validate(
        pipeline.config([attack_entry(name, levels) for name, levels in REPEAT.items()])
    )
    keys_before = pipeline.store.list()
    spy = Spy()
    report = run_config(pipeline.store, config, perturbation_factory=spy)
    assert spy.calls == 0
    assert pipeline.store.list() == keys_before, "run cached không ghi vào runs/<fingerprint>/"
    for outcome in report.outcomes:
        result = outcome.result
        assert result.status == "skipped"
        assert result.status_reason is not None and result.status_reason.code == "cached"
        first = next(r for r in sweep.results.values() if r.fingerprint == result.fingerprint)
        assert result.manifest_uri == first.manifest_uri


def test_force_writes_to_reruns_and_keeps_original(pipeline: Pipeline, forced: Rerun) -> None:
    store = pipeline.store
    for key, digest in forced.original_hashes.items():
        assert hashlib.sha256(store.get(key)).hexdigest() == digest
    for result in forced.results.values():
        assert result.status == "completed"
        assert result.manifest_uri == (
            f"runs/{result.fingerprint}/reruns/{result.run_id}/manifest.json"
        )
        assert store.exists(f"runs/{result.fingerprint}/reruns/{result.run_id}/result.json")


def _assert_close(a: RunResult, b: RunResult) -> None:
    assert a.metrics is not None and b.metrics is not None
    assert b.metrics.attacked.map50 == pytest.approx(a.metrics.attacked.map50, abs=MAP_TOL)
    rate_a, rate_b = a.metrics.attack_success_rate, b.metrics.attack_success_rate
    assert (rate_a is None) == (rate_b is None)
    if rate_a is not None and rate_b is not None:
        assert rate_b == pytest.approx(rate_a, abs=ASR_TOL)


def test_force_result_within_tolerance(sweep: Sweep, forced: Rerun) -> None:
    for key, result in forced.results.items():
        _assert_close(sweep.results[key], result)


def test_batch_size_1_and_5_within_tolerance(sweep: Sweep, batch1: Rerun) -> None:
    for key, result in batch1.results.items():
        _assert_close(sweep.results[key], result)


def test_golden_values(sweep: Sweep, golden: dict[str, Any]) -> None:
    tolerance = golden["tolerance"]
    assert sweep.results[("fgsm", 0.0)].metrics is not None
    for entry in golden["runs"]:
        metrics = sweep.results[(entry["attack"], float(entry["level"]))].metrics
        assert metrics is not None
        assert metrics.clean.map50 == pytest.approx(golden["clean_map50"], abs=tolerance)
        assert metrics.attacked.map50 == pytest.approx(entry["attacked_map50"], abs=tolerance)
        assert metrics.attack_success_rate == pytest.approx(
            entry["attack_success_rate"], abs=tolerance
        )


# ---------------------------------------------------------------- bổ sung độ phủ (kickoff)


def test_attack_labels_are_ground_truth(pipeline: Pipeline, sweep: Sweep, git_commit: None) -> None:
    config = LocalRunConfig.model_validate(pipeline.config([attack_entry("fgsm", [4])]))
    spy = Spy()
    run_config(pipeline.store, config, force=True, perturbation_factory=spy)
    loader = pipeline.loader()
    expected = next(loader.batches(5)).targets
    assert len(spy.targets) == len(expected)
    for got, want in zip(spy.targets, expected, strict=True):
        # Không có scores: nhãn là ground truth, không phải prediction. Phase 6 thêm `image_id`
        # (bắt buộc, seed theo ảnh) và `ignore_boxes` (tùy chọn, occlusion) vào interface.
        assert (
            {"boxes", "labels", "image_id"}
            <= set(got)
            <= {
                "boxes",
                "labels",
                "image_id",
                "ignore_boxes",
            }
        )
        assert (got["boxes"] == want["boxes"]).all() and (got["labels"] == want["labels"]).all()


def test_clean_map_comes_from_phase1_cache(
    pipeline: Pipeline,
    sweep: Sweep,
    git_commit: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    out = tmp_path / "eval.json"
    run_cli(
        pipeline.store_dir,
        "eval",
        "--model",
        pipeline.model["id"],
        "--slice",
        pipeline.slice["id"],
        "--mapping",
        pipeline.mapping["id"],
        "--out",
        str(out),
        "--device",
        "cpu",
    )
    evaluated = json.loads(out.read_text())
    assert evaluated["cache"]["hit"], "sweep phải đã tạo cache prediction ảnh sạch"

    def no_predict(*args: object, **kwargs: object) -> None:
        raise AssertionError("prediction ảnh sạch phải lấy từ cache")

    monkeypatch.setattr(run_module, "predict_slice", no_predict)
    config = LocalRunConfig.model_validate(pipeline.config([attack_entry("fgsm", [4])]))
    result = run_config(pipeline.store, config, force=True).outcomes[0].result
    assert result.metrics is not None
    assert result.metrics.clean.map50 == pytest.approx(evaluated["metrics"]["map50"], abs=1e-9)


def test_experiment_id_environment_and_cost(pipeline: Pipeline, sweep: Sweep) -> None:
    normalized = LocalRunConfig.model_validate(sweep.config).model_dump(mode="json")
    expected = content_id(sha256_of(normalized))
    for result in sweep.results.values():
        assert result.experiment_id == expected
        assert result.cost is None and result.gpu_seconds > 0
        manifest = _manifest(pipeline, result)
        assert manifest.environment.compute_target_id is None
        assert manifest.environment.gpu_model is None  # chạy trên CPU
        assert manifest.fingerprint_inputs.docker_image_digest == "none"
        assert manifest.fingerprint_inputs.git_commit == COMMIT


def test_run_show(pipeline: Pipeline, sweep: Sweep, forced: Rerun) -> None:
    fp = sweep.results[("pgd_linf", 4.0)].fingerprint
    shown = run_cli(pipeline.store_dir, "run", "show", fp)
    assert RunResult.model_validate_json(shown.stdout) == sweep.results[("pgd_linf", 4.0)]
    assert "manifest.json" in shown.stderr and "/cases/" in shown.stderr
    assert "reruns" in shown.stderr
    missing = run_cli(pipeline.store_dir, "run", "show", "0" * 64, code=1)
    assert "Không có run" in missing.stderr


def test_summary_table_columns(sweep: Sweep) -> None:
    for column in (
        "attack",
        "level",
        "mAP sạch",
        "mAP tấn công",
        "relative drop",
        "ASR",
        "trạng thái",
    ):
        assert column in sweep.stderr
