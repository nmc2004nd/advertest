"""Nghiệm thu Phase 2, mục Tính đúng của attack (validation.md). YOLOv8n thật, 5 ảnh fixture."""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest
import torch

from attacks.art_adapter import build_perturbation
from attacks.registry import get_spec, load_catalog
from ml_core.data.loader import Batch
from ml_core.models.estimator import build_estimator
from ml_core.models.gradient_check import batchnorm_stats, state_hash
from ml_core.models.wrapper import (
    DEFAULT_INFERENCE_PARAMS,
    UltralyticsDetector,
    load_detection_model,
)

from .conftest import WEIGHTS, Sweep

EPS8 = 8 / 255


@pytest.fixture(scope="module")
def detector() -> UltralyticsDetector:
    return UltralyticsDetector(load_detection_model(WEIGHTS), DEFAULT_INFERENCE_PARAMS)


@pytest.fixture(scope="module")
def estimator(detector: UltralyticsDetector) -> Any:
    return build_estimator(detector)


@pytest.fixture(scope="module")
def attacked(estimator: Any, batch: Batch, mask: np.ndarray) -> dict[str, np.ndarray]:
    """Ảnh sau tấn công của 3 attack trên cả 5 ảnh: fgsm/pgd_linf eps 8, pgd_l2 eps 2."""
    catalog = load_catalog()
    out = {}
    for name, level in (("fgsm", 8), ("pgd_linf", 8), ("pgd_l2", 2)):
        perturbation = build_perturbation(get_spec(catalog, name=name), estimator)
        out[name] = perturbation.apply(batch.images, batch.targets, level, seed=0, mask=mask)
    return out


def _real(mask: np.ndarray) -> np.ndarray:
    return np.broadcast_to(mask == 1, (mask.shape[0], 3, *mask.shape[2:]))


@pytest.mark.parametrize("name", ["fgsm", "pgd_linf", "pgd_l2"])
def test_level_zero_is_identity(name: str, estimator: Any, batch: Batch, mask: np.ndarray) -> None:
    perturbation = build_perturbation(get_spec(load_catalog(), name=name), estimator)
    out = perturbation.apply(batch.images, batch.targets, 0, seed=0, mask=mask)
    assert np.array_equal(out, batch.images)


@pytest.mark.parametrize("name", ["fgsm", "pgd_linf", "pgd_l2"])
def test_level_zero_metrics_equal_clean(name: str, sweep: Sweep) -> None:
    metrics = sweep.results[(name, 0.0)].metrics
    assert metrics is not None
    assert metrics.attacked == metrics.clean
    assert metrics.absolute_drop == 0 and metrics.relative_drop == 0


@pytest.mark.parametrize("name", ["fgsm", "pgd_linf"])
def test_linf_bound_on_real_region(
    name: str, attacked: dict[str, np.ndarray], batch: Batch, mask: np.ndarray
) -> None:
    delta = attacked[name] - batch.images
    assert np.abs(delta[_real(mask)]).max() <= EPS8 + 1e-6


def test_l2_bound_per_image(attacked: dict[str, np.ndarray], batch: Batch) -> None:
    delta = (attacked["pgd_l2"] - batch.images).reshape(len(batch.images), -1)
    assert (np.linalg.norm(delta.astype(np.float64), axis=1) <= 2 + 1e-4).all()


@pytest.mark.parametrize("name", ["fgsm", "pgd_linf", "pgd_l2"])
def test_pad_region_exactly_unchanged(
    name: str, attacked: dict[str, np.ndarray], batch: Batch, mask: np.ndarray
) -> None:
    pad = ~_real(mask)
    assert pad.any()
    delta = attacked[name] - batch.images
    assert np.all(delta[pad] == 0)  # so sánh chính xác, không sai số
    assert np.any(delta[_real(mask)] != 0)


@pytest.mark.parametrize("name", ["fgsm", "pgd_linf", "pgd_l2"])
def test_attacked_images_in_unit_range(name: str, attacked: dict[str, np.ndarray]) -> None:
    images = attacked[name]
    assert images.dtype == np.float32 and images.min() >= 0.0 and images.max() <= 1.0


def test_pgd_increases_loss_of_every_image(
    estimator: Any, attacked: dict[str, np.ndarray], batch: Batch
) -> None:
    for i in range(len(batch.images)):
        target = batch.targets[i : i + 1]
        clean = float(estimator.compute_loss(batch.images[i : i + 1], target))
        adv = float(estimator.compute_loss(attacked["pgd_linf"][i : i + 1], target))
        assert adv > clean, batch.image_ids[i]


def test_pgd_eps16_drops_map(sweep: Sweep) -> None:
    metrics = sweep.results[("pgd_linf", 16.0)].metrics
    assert metrics is not None
    assert metrics.attacked.map50 < metrics.clean.map50 - 0.1


def test_pgd_leaves_weights_and_batchnorm_unchanged(batch: Batch, mask: np.ndarray) -> None:
    detector = UltralyticsDetector(load_detection_model(WEIGHTS), DEFAULT_INFERENCE_PARAMS)
    hash_before, bn_before = state_hash(detector), batchnorm_stats(detector)
    assert bn_before
    perturbation = build_perturbation(
        get_spec(load_catalog(), name="pgd_linf"), build_estimator(detector)
    )
    perturbation.apply(batch.images[:2], batch.targets[:2], 8, seed=0, mask=mask[:2])
    assert state_hash(detector) == hash_before
    bn_after = batchnorm_stats(detector)
    assert all(torch.equal(bn_before[k], bn_after[k]) for k in bn_before)
