"""Nghiệm thu Phase 2, mục Trạng thái (validation.md)."""

from __future__ import annotations

import json
from typing import Any, cast

import pytest
import torch
from ultralytics.models import YOLO
from ultralytics.nn.tasks import DetectionModel

from advertest_contracts.models import ModelCard, RunResult
from attacks.art_adapter import ArtPerturbation, build_perturbation
from ml_core.runner.config import LocalRunConfig
from ml_core.runner.run import RunOutcome, run_config

from .conftest import Pipeline, Sweep, attack_entry, run_cli

ABNORMAL = {"failed", "skipped", "stopped_limit", "cancelled"}


class CountingFactory:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, spec: Any, estimator: Any) -> ArtPerturbation:
        self.calls += 1
        return build_perturbation(spec, estimator)


def _check_contract(outcomes: list[RunOutcome]) -> None:
    for outcome in outcomes:
        result = RunResult.model_validate_json(outcome.result.model_dump_json())
        if result.status in ABNORMAL:
            assert result.status_reason is not None and result.status_reason.message
        else:
            assert result.status_reason is None


@pytest.fixture(scope="module")
def random_model(pipeline: Pipeline, tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """YOLOv8n khởi tạo ngẫu nhiên: bài kiểm tra gradient thật không đạt."""
    torch.manual_seed(0)
    yolo = YOLO("yolov8n.yaml")
    model = cast(DetectionModel, yolo.model)
    model.names = {i: {0: "person", 2: "car", 7: "truck"}.get(i, f"class{i}") for i in range(80)}
    weights = tmp_path_factory.mktemp("random") / "yolov8n-random.pt"
    yolo.save(weights)
    card = json.loads(
        run_cli(
            pipeline.store_dir, "model", "register", "--weights", str(weights), "--name", "random"
        ).stdout
    )
    mapping = json.loads(
        run_cli(
            pipeline.store_dir,
            "mapping",
            "create",
            "--dataset",
            pipeline.dataset_sha256,
            "--model",
            card["id"],
        ).stdout
    )
    return {"card": card, "mapping": mapping}


@pytest.mark.usefixtures("git_commit")
def test_model_without_gradients_is_skipped(
    pipeline: Pipeline, sweep: Sweep, random_model: dict[str, Any]
) -> None:
    card = ModelCard.model_validate(random_model["card"])
    assert not card.supports_gradients
    config = LocalRunConfig.model_validate(
        pipeline.config(
            [attack_entry("fgsm", [4])],
            model_id=str(card.id),
            mapping_id=random_model["mapping"]["id"],
        )
    )
    factory = CountingFactory()
    report = run_config(pipeline.store, config, perturbation_factory=factory)
    (outcome,) = report.outcomes
    assert factory.calls == 0
    assert outcome.result.status == "skipped"
    assert outcome.result.status_reason is not None
    assert outcome.result.status_reason.code == "incompatible"
    assert outcome.prefix is not None and "/attempts/" in outcome.prefix
    assert pipeline.store.exists(f"{outcome.prefix}/result.json")
    _check_contract(report.outcomes)


def _failing_factory(spec: Any, estimator: Any) -> ArtPerturbation:
    class Failing(ArtPerturbation):
        def apply(
            self, images: Any, targets: Any, level: float, seed: int, mask: Any = None
        ) -> Any:
            if level == 6:
                raise RuntimeError("lỗi ép trong test nghiệm thu")
            return super().apply(images, targets, level, seed, mask)

    return Failing(spec, estimator)


@pytest.mark.usefixtures("git_commit")
def test_exception_fails_only_that_run(pipeline: Pipeline, sweep: Sweep) -> None:
    config = LocalRunConfig.model_validate(pipeline.config([attack_entry("fgsm", [2, 6, 10])]))
    report = run_config(pipeline.store, config, perturbation_factory=_failing_factory)
    statuses = [o.result.status for o in report.outcomes]
    assert statuses == ["completed", "failed", "completed"]
    failed = report.outcomes[1]
    assert failed.result.status_reason is not None
    assert failed.result.status_reason.code == "error"
    assert "lỗi ép trong test nghiệm thu" in failed.result.status_reason.message
    assert failed.prefix is not None and "/attempts/" in failed.prefix
    assert not pipeline.store.exists(f"runs/{failed.result.fingerprint}/result.json")
    _check_contract(report.outcomes)


def test_every_sweep_result_validates(sweep: Sweep) -> None:
    for result in sweep.results.values():
        again = RunResult.model_validate_json(result.model_dump_json())
        assert again.status == "completed" and again.status_reason is None
        assert again.metrics is not None and again.manifest_uri is not None
