from pathlib import Path

import numpy as np
import pytest
import torch
from numpy.typing import NDArray
from torch import nn

from ml_core.models.estimator import build_estimator
from ml_core.models.gradient_check import batchnorm_stats, run_gradient_check, state_hash
from ml_core.models.tests.conftest import LOW_PARAMS
from ml_core.models.wrapper import UltralyticsDetector, load_detection_model


class _FakeDetector(nn.Module):
    """Model giả theo cùng giao diện với UltralyticsDetector.

    `mode="good"`: loss = tổng bình phương đầu ra BatchNorm (eval), bước theo dấu gradient làm tăng.
    `mode="zero"`: loss không phụ thuộc ảnh (gradient bằng 0).
    `mode="mutate"`: gradient khác 0 nhưng mỗi lần tính loss lại sửa running stats của BatchNorm.
    """

    def __init__(self, mode: str) -> None:
        super().__init__()
        self.mode = mode
        self.bn = nn.BatchNorm2d(3)
        self.bias = nn.Parameter(torch.tensor(1.0))
        self.running_mean.fill_(0.5)

    @property
    def running_mean(self) -> torch.Tensor:
        value = self.bn.running_mean
        assert value is not None
        return value

    def train(self, mode: bool = True) -> "_FakeDetector":
        self.training = mode
        self.bn.eval()
        return self

    def forward(
        self, x: torch.Tensor, targets: torch.Tensor | None = None
    ) -> dict[str, torch.Tensor] | list[dict[str, torch.Tensor]]:
        if self.training:
            if self.mode == "good":
                loss = self.bn(x).pow(2).sum()
            elif self.mode == "zero":
                loss = x.sum() * 0 + self.bias
            else:
                with torch.no_grad():
                    self.running_mean.add_(1)
                loss = (x**2).sum()
            return {"loss_total": loss}
        empty = torch.zeros((0,))
        return [
            {"boxes": torch.zeros((0, 4)), "labels": empty.long(), "scores": empty}
            for _ in range(len(x))
        ]


def test_differentiable_model_passes(images: NDArray[np.float32]) -> None:
    fake = _FakeDetector("good")
    estimator = build_estimator(fake, LOW_PARAMS)
    check = run_gradient_check(estimator, images, LOW_PARAMS.operating_conf)
    assert check.passed, check.details
    assert check.details is None
    assert check.checked_at.utcoffset() is not None


def test_random_yolo_gradient_valid_and_model_unchanged(
    random_weights: Path, images: NDArray[np.float32]
) -> None:
    """YOLO khởi tạo ngẫu nhiên có loss gần như phẳng theo ảnh, nên điều kiện "loss tăng" có thể
    fail; các điều kiện còn lại (gradient hợp lệ, model không đổi) phải đạt. Weights thật được
    kiểm ở test nghiệm thu trên fixture."""
    detector = UltralyticsDetector(load_detection_model(random_weights), LOW_PARAMS)
    estimator = build_estimator(detector, LOW_PARAMS)
    hash_before = state_hash(detector)
    bn_before = batchnorm_stats(detector)
    assert bn_before  # YOLOv8 có BatchNorm

    check = run_gradient_check(estimator, images, LOW_PARAMS.operating_conf)

    for reason in ("NaN", "toàn 0", "BatchNorm", "state_dict"):
        assert reason not in (check.details or "")
    assert state_hash(detector) == hash_before
    bn_after = batchnorm_stats(detector)
    assert all(torch.equal(bn_before[k], bn_after[k]) for k in bn_before)


def test_loss_gradient_leaves_model_unchanged(
    random_weights: Path, images: NDArray[np.float32]
) -> None:
    detector = UltralyticsDetector(load_detection_model(random_weights), LOW_PARAMS)
    estimator = build_estimator(detector, LOW_PARAMS)
    before = state_hash(detector)
    targets = [{"boxes": np.array([[10.0, 10.0, 100.0, 120.0]]), "labels": np.array([2])}] * 2
    estimator.loss_gradient(images, targets)
    assert state_hash(detector) == before


@pytest.mark.parametrize(
    ("mode", "reason"),
    [("zero", "gradient toàn 0"), ("mutate", "BatchNorm")],
)
def test_fake_models_fail(mode: str, reason: str, images: NDArray[np.float32]) -> None:
    estimator = build_estimator(_FakeDetector(mode), LOW_PARAMS)
    check = run_gradient_check(estimator, images, LOW_PARAMS.operating_conf)
    assert not check.passed
    assert check.details is not None and reason in check.details
