"""Nghiệm thu Phase 1, mục Model (validation.md). Weights YOLOv8n và 5 ảnh KITTI của fixture."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import torch
from ultralytics import YOLO

from advertest_contracts.ids import content_id
from advertest_contracts.models import ModelCard
from ml_core.models.estimator import build_estimator
from ml_core.models.gradient_check import (
    batchnorm_stats,
    run_gradient_check,
    self_targets,
    state_hash,
)
from ml_core.models.register import load_check_images
from ml_core.models.wrapper import (
    DEFAULT_INFERENCE_PARAMS,
    UltralyticsDetector,
    load_detection_model,
)

from .conftest import WEIGHTS, Pipeline, run_cli


def _box_iou(a: torch.Tensor, b: torch.Tensor) -> torch.Tensor:
    lt = torch.maximum(a[:, None, :2], b[None, :, :2])
    rb = torch.minimum(a[:, None, 2:], b[None, :, 2:])
    inter = (rb - lt).clamp(min=0).prod(dim=2)
    area_a = (a[:, 2:] - a[:, :2]).prod(dim=1)
    area_b = (b[:, 2:] - b[:, :2]).prod(dim=1)
    return inter / (area_a[:, None] + area_b[None, :] - inter).clamp(min=1e-9)


@pytest.fixture(scope="module")
def images() -> np.ndarray:
    return load_check_images()


@pytest.fixture(scope="module")
def detector() -> UltralyticsDetector:
    return UltralyticsDetector(load_detection_model(WEIGHTS), DEFAULT_INFERENCE_PARAMS)


def test_wrapper_matches_ultralytics_predict(
    detector: UltralyticsDetector, images: np.ndarray
) -> None:
    with torch.no_grad():
        ours = detector(torch.from_numpy(images))
    params = DEFAULT_INFERENCE_PARAMS
    reference = YOLO(str(WEIGHTS)).predict(
        source=torch.from_numpy(images),
        conf=params.conf,
        iou=params.iou,
        max_det=params.max_det,
        verbose=False,
    )
    assert isinstance(ours, list) and len(ours) == len(reference) == 5
    for mine, ref in zip(ours, reference, strict=True):
        ref_boxes = torch.as_tensor(ref.boxes.xyxy)
        assert len(mine["boxes"]) == len(ref_boxes) > 0
        iou = _box_iou(mine["boxes"], ref_boxes)
        matched = iou.argmax(dim=1)
        assert torch.all(iou.max(dim=1).values >= 0.99)
        assert torch.equal(mine["labels"], torch.as_tensor(ref.boxes.cls)[matched].long())
        assert torch.all((mine["scores"] - torch.as_tensor(ref.boxes.conf)[matched]).abs() < 1e-3)


def test_predict_output_format(images: np.ndarray) -> None:
    estimator = build_estimator(load_detection_model(WEIGHTS))
    preds = estimator.predict(images)
    assert len(preds) == len(images)
    for p in preds:
        k = len(p["boxes"])
        assert (
            p["boxes"].shape == (k, 4) and p["labels"].shape == (k,) and p["scores"].shape == (k,)
        )


def test_gradient_valid_step_increases_loss_model_unchanged(images: np.ndarray) -> None:
    detector = UltralyticsDetector(load_detection_model(WEIGHTS), DEFAULT_INFERENCE_PARAMS)
    estimator = build_estimator(detector)
    hash_before, bn_before = state_hash(detector), batchnorm_stats(detector)
    assert bn_before

    targets = self_targets(estimator, images, DEFAULT_INFERENCE_PARAMS.operating_conf)
    grad = estimator.loss_gradient(images, targets)
    assert grad.shape == images.shape  # loss_gradient chạy với (N, 3, 640, 640)
    assert np.all(np.isfinite(grad)) and np.any(grad != 0)

    loss = float(estimator.compute_loss(images, targets))
    stepped = np.clip(images + 2 / 255 * np.sign(grad), 0, 1).astype(np.float32)
    assert float(estimator.compute_loss(stepped, targets)) > loss

    assert state_hash(detector) == hash_before
    bn_after = batchnorm_stats(detector)
    assert all(torch.equal(bn_before[k], bn_after[k]) for k in bn_before)


def test_register_fixture_weights(pipeline: Pipeline) -> None:
    card = ModelCard.model_validate(pipeline.model)
    assert card.supports_gradients and card.gradient_check.passed
    assert card.id == content_id(card.weights_sha256)
    assert card.architecture == "yolov8n" and card.class_names[0] == "person"


def test_register_again_same_id(pipeline: Pipeline) -> None:
    again = json.loads(
        run_cli(
            pipeline.store_dir,
            "model",
            "register",
            "--weights",
            str(WEIGHTS),
            "--name",
            "yolov8n-coco",
        )
    )
    assert again["id"] == pipeline.model["id"]


def test_zero_gradient_model_not_supported(images: np.ndarray) -> None:
    class ZeroGradient(torch.nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.bias = torch.nn.Parameter(torch.tensor(1.0))

        def forward(self, x: torch.Tensor, targets: torch.Tensor | None = None) -> object:
            if self.training:
                return {"loss_total": x.sum() * 0 + self.bias}
            empty = torch.zeros(0)
            return [
                {"boxes": torch.zeros((0, 4)), "labels": empty.long(), "scores": empty} for _ in x
            ]

    check = run_gradient_check(build_estimator(ZeroGradient()), images[:2], 0.25)
    assert not check.passed
    assert check.details and "gradient" in check.details


def test_register_writes_card_in_store(pipeline: Pipeline) -> None:
    sha = pipeline.model["weights_sha256"]
    card = Path(pipeline.store_dir) / "models" / sha / "card.json"
    assert ModelCard.model_validate_json(card.read_text()).id == content_id(sha)
