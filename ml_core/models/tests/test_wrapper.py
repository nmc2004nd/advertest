from pathlib import Path

import numpy as np
import pytest
import torch
from numpy.typing import NDArray
from torchvision.ops import box_iou
from ultralytics.models import YOLO

from ml_core.models.tests.conftest import LOW_PARAMS
from ml_core.models.wrapper import LOSS_KEYS, UltralyticsDetector, load_detection_model


@pytest.fixture
def detector(random_weights: Path) -> UltralyticsDetector:
    return UltralyticsDetector(load_detection_model(random_weights), LOW_PARAMS)


def test_predict_format(detector: UltralyticsDetector, images: NDArray[np.float32]) -> None:
    with torch.no_grad():
        preds = detector(torch.from_numpy(images))
    assert isinstance(preds, list) and len(preds) == len(images)
    assert sum(len(p["boxes"]) for p in preds) > 0
    for p in preds:
        k = len(p["boxes"])
        assert p["boxes"].shape == (k, 4)
        assert p["labels"].shape == (k,) and p["labels"].dtype == torch.int64
        assert p["scores"].shape == (k,)
        assert torch.all(p["boxes"][:, 2] >= p["boxes"][:, 0])
        assert torch.all(p["boxes"][:, 3] >= p["boxes"][:, 1])
        assert p["boxes"].min() >= 0 and p["boxes"].max() <= 640
        assert len(p["boxes"]) <= LOW_PARAMS.max_det


def test_predict_matches_ultralytics(
    detector: UltralyticsDetector, random_weights: Path, images: NDArray[np.float32]
) -> None:
    with torch.no_grad():
        mine = detector(torch.from_numpy(images))
    reference = YOLO(str(random_weights)).predict(
        source=torch.from_numpy(images),
        conf=LOW_PARAMS.conf,
        iou=LOW_PARAMS.iou,
        max_det=LOW_PARAMS.max_det,
        verbose=False,
    )
    for ours, ref in zip(mine, reference, strict=True):
        assert len(ours["boxes"]) == len(ref.boxes) > 0
        iou = box_iou(ours["boxes"], ref.boxes.xyxy)
        matched = iou.argmax(dim=1)
        assert torch.all(iou.max(dim=1).values >= 0.99)
        assert torch.equal(ours["labels"], ref.boxes.cls[matched].long())
        assert torch.all((ours["scores"] - ref.boxes.conf[matched]).abs() < 1e-3)


def test_inner_model_stays_eval_and_frozen(detector: UltralyticsDetector) -> None:
    detector.train()
    assert detector.training
    assert not detector.model.training
    assert all(not m.training for m in detector.model.modules())
    assert all(not p.requires_grad for p in detector.model.parameters())


def test_loss_mode_differentiable(
    detector: UltralyticsDetector, images: NDArray[np.float32]
) -> None:
    x = torch.from_numpy(images).requires_grad_(True)
    targets = torch.tensor([[0, 2, 0.5, 0.5, 0.2, 0.3], [1, 0, 0.3, 0.6, 0.1, 0.2]])
    detector.train()
    losses = detector(x, targets)
    assert isinstance(losses, dict) and set(losses) == set(LOSS_KEYS)
    assert losses["loss_total"].ndim == 0
    losses["loss_total"].backward()
    assert x.grad is not None and torch.any(x.grad != 0)


def test_loss_mode_requires_targets(
    detector: UltralyticsDetector, images: NDArray[np.float32]
) -> None:
    detector.train()
    with pytest.raises(ValueError):
        detector(torch.from_numpy(images))
