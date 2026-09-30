"""Calibration cost profile (requirements.md Phase 3, Calibration và ước lượng).

Chạy trên n = min(20, số ảnh của slice) ảnh đầu; tăng batch size 1, 2, 4, ... tối đa min(n, 32);
dừng khi hết VRAM (giữ bậc trước) hoặc, trên CPU, khi `sec_per_image` không giảm so với bậc
trước (giữ bậc trước). Đo `sec_per_image` (attack + predict) và `peak_vram_mb` ở batch size được
chọn. Có một lượt khởi động trước khi đo để thời gian nạp lần đầu không làm lệch bậc 1.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

import numpy as np
import torch

from advertest_contracts.models import CostProfile, Environment
from advertest_contracts.perturbation import Perturbation
from ml_core.data.loader import SliceLoader
from ml_core.runner.images import letterbox_mask

logger = logging.getLogger(__name__)
MAX_IMAGES = 20
MAX_BATCH = 32


@dataclass(frozen=True)
class Measurement:
    batch_size: int
    sec_per_image: float
    peak_vram_mb: int


def batch_sizes(n_images: int) -> list[int]:
    """1, 2, 4, ... không vượt quá min(n, 32)."""
    cap = min(n_images, MAX_BATCH)
    sizes, size = [], 1
    while size <= cap:
        sizes.append(size)
        size *= 2
    return sizes


def _is_cuda(device: str) -> bool:
    return device.startswith("cuda")


def measure(
    loader: SliceLoader,
    image_ids: list[str],
    estimator: Any,
    perturbation: Perturbation,
    level: float,
    seed: int,
    device: str,
) -> Measurement:
    """Attack + predict một batch gồm `image_ids`."""
    loaded = [loader.load(image_id) for image_id in image_ids]
    images = np.stack([item[0] for item in loaded])
    targets = [item[1] for item in loaded]
    mask = letterbox_mask([item[3] for item in loaded])
    if _is_cuda(device):
        torch.cuda.reset_peak_memory_stats(device)
    start = time.perf_counter()
    adversarial = perturbation.apply(images, targets, level, seed, mask)
    estimator.predict(adversarial, batch_size=len(image_ids))
    elapsed = time.perf_counter() - start
    peak = int(torch.cuda.max_memory_allocated(device) / 2**20) if _is_cuda(device) else 0
    return Measurement(len(image_ids), elapsed / len(image_ids), peak)


def calibrate(
    *,
    loader: SliceLoader,
    estimator: Any,
    perturbation: Perturbation,
    level: float,
    seed: int,
    device: str,
    compute_target_id: UUID,
    model_version_id: UUID,
    attack_spec_id: UUID,
    environment: Environment,
    now: datetime,
) -> CostProfile:
    ids = loader.slice.image_ids[:MAX_IMAGES]
    measure(loader, ids[:1], estimator, perturbation, level, seed, device)  # khởi động
    best: Measurement | None = None
    for size in batch_sizes(len(ids)):
        try:
            current = measure(loader, ids[:size], estimator, perturbation, level, seed, device)
        except torch.cuda.OutOfMemoryError:
            logger.warning("Hết VRAM ở batch size %d; giữ batch size trước", size)
            if best is None:
                raise
            break
        finally:
            if _is_cuda(device):
                torch.cuda.empty_cache()
        logger.info("Calibration batch %d: %.3f s/ảnh", size, current.sec_per_image)
        if (
            best is not None
            and not _is_cuda(device)
            and current.sec_per_image >= best.sec_per_image
        ):
            break
        best = current
    assert best is not None  # batch_sizes luôn có ít nhất bậc 1
    return CostProfile(
        compute_target_id=compute_target_id,
        model_version_id=model_version_id,
        attack_spec_id=attack_spec_id,
        sec_per_image=max(best.sec_per_image, 1e-6),
        peak_vram_mb=best.peak_vram_mb,
        batch_size=best.batch_size,
        measured_at=now,
        environment=environment,
    )
