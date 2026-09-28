"""Nghiệm thu Phase 1, mục Đánh giá và cache (validation.md)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from advertest_contracts.ids import content_id
from advertest_contracts.models import (
    ClassMapping,
    ClassMappingBody,
    CleanEvalResult,
    compute_mapping_sha256,
)
from ml_core.cli import evaluate as evaluate_module
from ml_core.cli.evaluate import run_eval
from ml_core.data.mapping import save_mapping
from ml_core.models.wrapper import DEFAULT_INFERENCE_PARAMS
from ml_core.store import LocalStore

from .conftest import Pipeline, run_cli


def _eval_cli(pipeline: Pipeline, out: Path, mapping_id: str | None = None) -> CleanEvalResult:
    run_cli(
        pipeline.store_dir,
        "eval",
        "--model",
        pipeline.model["id"],
        "--slice",
        pipeline.slice["id"],
        "--mapping",
        mapping_id or pipeline.mapping["id"],
        "--out",
        str(out),
        "--device",
        "cpu",
    )
    return CleanEvalResult.model_validate(json.loads(out.read_text()))


def _no_model(*args: object, **kwargs: object) -> None:
    raise AssertionError("model không được nạp khi cache hit")


@pytest.fixture(scope="module")
def first_run(pipeline: Pipeline, tmp_path_factory: pytest.TempPathFactory) -> CleanEvalResult:
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("GIT_COMMIT", "0" * 40)
        return _eval_cli(pipeline, tmp_path_factory.mktemp("eval") / "first.json")


def test_eval_output_validates(first_run: CleanEvalResult, pipeline: Pipeline) -> None:
    assert first_run.slice.id == UUID(pipeline.slice["id"])
    assert first_run.num_images == 5


def test_map_matches_golden(first_run: CleanEvalResult, golden: dict[str, Any]) -> None:
    tol = golden["tolerance"]
    assert first_run.slice.dataset_version_sha256 == golden["dataset_version_sha256"]
    assert first_run.metrics.map50 == pytest.approx(golden["map50"], abs=tol)
    assert first_run.metrics.map50_95 == pytest.approx(golden["map50_95"], abs=tol)


@pytest.mark.usefixtures("git_commit")
def test_second_run_hits_cache_without_model(
    first_run: CleanEvalResult, pipeline: Pipeline, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(evaluate_module, "load_detection_model", _no_model)
    second = _eval_cli(pipeline, tmp_path / "second.json")
    assert second.cache.hit and second.cache.key == first_run.cache.key
    assert second.metrics == first_run.metrics


@pytest.mark.usefixtures("git_commit")
def test_changing_conf_misses_cache(first_run: CleanEvalResult, pipeline: Pipeline) -> None:
    params = DEFAULT_INFERENCE_PARAMS.model_copy(update={"conf": 0.01})
    run = run_eval(
        LocalStore(pipeline.store_dir),
        UUID(pipeline.model["id"]),
        UUID(pipeline.slice["id"]),
        UUID(pipeline.mapping["id"]),
        "cpu",
        params=params,
    )
    assert not run.result.cache.hit and run.result.cache.key != first_run.cache.key


@pytest.mark.usefixtures("git_commit")
def test_changing_mapping_hits_cache_and_recomputes(
    first_run: CleanEvalResult, pipeline: Pipeline, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = ClassMapping.model_validate(pipeline.mapping)
    body = ClassMappingBody(
        dataset_version_sha256=base.dataset_version_sha256,
        model_id=base.model_id,
        preset=None,
        classes=base.classes,
        difficulty=None,  # không lọc độ khó: nhiều ground truth hơn
    )
    sha = compute_mapping_sha256(body)
    other = ClassMapping(**body.model_dump(), id=content_id(sha), mapping_sha256=sha)
    save_mapping(LocalStore(pipeline.store_dir), other)

    monkeypatch.setattr(evaluate_module, "load_detection_model", _no_model)
    result = _eval_cli(pipeline, tmp_path / "other_mapping.json", str(other.id))
    assert result.cache.hit and result.cache.key == first_run.cache.key
    assert result.class_mapping.id == other.id
    assert result.metrics.per_class["car"].num_gt > first_run.metrics.per_class["car"].num_gt


def test_inference_params_recorded(first_run: CleanEvalResult) -> None:
    p = first_run.inference_params
    assert (p.conf, p.iou, p.max_det, p.operating_conf) == (0.001, 0.7, 300, 0.25)
