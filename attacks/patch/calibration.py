"""Đo chi phí train patch cho cost profile (requirements.md Phase 6, mục Ước lượng; task 14).

`sec_per_image_iteration` = thời gian của `iterations` vòng train (gồm tính giá trị mục tiêu) chia
cho số vòng và số ảnh. Dùng patch ở `area_ratio` lớn nhất của spec; chi phí gần như không phụ thuộc
kích thước patch. Batch size là `spec.training.batch_size` như khi train thật.
"""

from __future__ import annotations

from art.estimators.estimator import BaseEstimator

from advertest_contracts.models import AttackSpec
from advertest_contracts.perturbation import ImageBatch, MaskBatch
from attacks.patch.training import PatchTrainer

CALIBRATION_ITERATIONS = 5


def measure_sec_per_image_iteration(
    spec: AttackSpec,
    estimator: BaseEstimator,
    images: ImageBatch,
    mask: MaskBatch | None,
    *,
    iterations: int = CALIBRATION_ITERATIONS,
    seed: int = 0,
) -> float:
    if iterations < 1 or len(images) == 0:
        raise ValueError("Cần ít nhất một vòng lặp và một ảnh")
    trainer = PatchTrainer(spec, estimator, area_ratio=spec.primary_param.max, seed=seed)
    state = trainer.train(images, mask, max_iter=iterations)
    return state.seconds / (iterations * len(images))
