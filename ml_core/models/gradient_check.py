"""Bài kiểm tra gradient quyết định `ModelCard.supports_gradients`.

Pass khi (requirements.md Phase 1, mục Đăng ký model; validation.md mục Model):
1. gradient theo ảnh hữu hạn và không toàn 0;
2. một bước `x + 2/255 · sign(grad)` (cắt về [0, 1]) làm loss tăng;
3. model không đổi: hash `state_dict` và running mean/var của BatchNorm giữ nguyên.

Target là prediction của chính model trên ảnh sạch có score ≥ `operating_conf`
(giống attack untargeted ở Phase 2), nên bài kiểm tra không phụ thuộc ground truth hay mapping.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

import numpy as np
import torch
from art.estimators.object_detection import PyTorchObjectDetector
from numpy.typing import NDArray

from advertest_contracts.models import GradientCheck

STEP = 2 / 255


def state_hash(module: torch.nn.Module) -> str:
    """sha256 của toàn bộ `state_dict` (tham số và buffer, gồm running stats của BatchNorm)."""
    digest = hashlib.sha256()
    for name, tensor in module.state_dict().items():
        digest.update(name.encode())
        digest.update(tensor.detach().cpu().contiguous().numpy().tobytes())
    return digest.hexdigest()


def batchnorm_stats(module: torch.nn.Module) -> dict[str, torch.Tensor]:
    stats: dict[str, torch.Tensor] = {}
    for name, layer in module.named_modules():
        if isinstance(layer, torch.nn.modules.batchnorm._BatchNorm):
            for attr in ("running_mean", "running_var"):
                value = getattr(layer, attr)
                if value is not None:
                    stats[f"{name}.{attr}"] = value.detach().clone()
    return stats


def self_targets(
    estimator: PyTorchObjectDetector, images: NDArray[np.float32], operating_conf: float
) -> list[dict[str, NDArray[Any]]]:
    """Prediction của model trên ảnh sạch có score ≥ `operating_conf`, dạng label của ART."""
    targets = []
    for pred in estimator.predict(images):
        keep = pred["scores"] >= operating_conf
        targets.append({"boxes": pred["boxes"][keep], "labels": pred["labels"][keep]})
    return targets


def run_gradient_check(
    estimator: PyTorchObjectDetector, images: NDArray[np.float32], operating_conf: float
) -> GradientCheck:
    """Chạy bài kiểm tra trên `images` (N, 3, H, W) float32 [0, 1]; không ném lỗi khi fail."""
    module = estimator.model
    hash_before = state_hash(module)
    bn_before = batchnorm_stats(module)

    targets = self_targets(estimator, images, operating_conf)
    grad = np.asarray(estimator.loss_gradient(images, targets))
    failures: list[str] = []
    if not np.all(np.isfinite(grad)):
        failures.append("gradient có NaN hoặc Inf")
    elif not np.any(grad != 0):
        failures.append("gradient toàn 0")
    else:
        loss_clean = float(estimator.compute_loss(images, targets))
        stepped = np.clip(images + STEP * np.sign(grad), 0.0, 1.0).astype(np.float32)
        loss_stepped = float(estimator.compute_loss(stepped, targets))
        if not loss_stepped > loss_clean:
            failures.append(
                f"bước 2/255 theo dấu gradient không làm loss tăng "
                f"({loss_clean:.6g} → {loss_stepped:.6g})"
            )

    bn_after = batchnorm_stats(module)
    if bn_after.keys() != bn_before.keys() or any(
        not torch.equal(bn_before[k], bn_after[k]) for k in bn_before
    ):
        failures.append("running stats của BatchNorm bị thay đổi")
    if state_hash(module) != hash_before:
        failures.append("state_dict của model bị thay đổi")

    return GradientCheck(
        passed=not failures,
        checked_at=datetime.now(UTC),
        details="; ".join(failures) or None,
    )
