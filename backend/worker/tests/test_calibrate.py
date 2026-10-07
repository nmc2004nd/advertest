"""Calibration trên CPU (validation.md Phase 3, Calibration và ước lượng)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

import pytest

from advertest_contracts.models import CostProfile, Environment
from advertest_worker.calibrate import (
    batch_sizes,
    calibrate,
    calibration_patch,
    patch_training_cost,
)
from attacks.art_adapter import build_perturbation
from attacks.factory import build_perturbation as build_any_perturbation
from attacks.registry import get_spec, load_catalog
from ml_core.cli.evaluate import load_model_from_store
from ml_core.data.loader import SliceLoader
from ml_core.models.estimator import build_estimator
from ml_core.models.register import load_card
from ml_core.runner.images import letterbox_mask
from ml_core.runner.tests.test_run import Base, _build
from ml_core.store import LocalStore


def test_batch_sizes_capped() -> None:
    assert batch_sizes(1) == [1]
    assert batch_sizes(5) == [1, 2, 4]
    assert batch_sizes(20) == [1, 2, 4, 8, 16]
    assert batch_sizes(300) == [1, 2, 4, 8, 16, 32]


@pytest.fixture(scope="module")
def base(tmp_path_factory: pytest.TempPathFactory) -> Base:
    return _build(tmp_path_factory.mktemp("calibrate"), supports_gradients=True)


def test_calibrate_on_cpu_gives_valid_profile(base: Base) -> None:
    store = LocalStore(base.root)
    loader = SliceLoader.from_ids(store, UUID(base.slice_id), UUID(base.mapping_id))
    card = load_card(store, base.card.weights_sha256)
    estimator = build_estimator(load_model_from_store(store, card.weights_sha256), device="cpu")
    spec = get_spec(load_catalog(), name="fgsm")
    target = uuid4()
    env = Environment(
        compute_target_id=target, gpu_model=None, cuda_version=None, driver_version=None
    )
    profile = calibrate(
        loader=loader,
        estimator=estimator,
        perturbation=build_perturbation(spec, estimator),
        level=4.0,
        seed=0,
        device="cpu",
        compute_target_id=target,
        model_version_id=card.id,
        attack_spec_id=spec.id,
        environment=env,
        now=datetime(2026, 9, 29, tzinfo=UTC),
    )
    CostProfile.model_validate(profile.model_dump())
    assert profile.batch_size in (1, 2)  # 3 ảnh: n = 3, trần min(3, 32) → bậc 1, 2
    assert profile.peak_vram_mb == 0 and profile.sec_per_image > 0


@pytest.mark.parametrize(("name", "level"), [("fog", 3.0), ("bbox_occlusion", 0.5)])
def test_calibrate_corruption_and_occlusion(base: Base, name: str, level: float) -> None:
    """Phase 6: target của batch đo có `image_id` (seed theo ảnh) như khi chạy run; trước đây
    calibration của corruption, occlusion ném lỗi và làm experiment kẹt ở `running`."""
    store = LocalStore(base.root)
    loader = SliceLoader.from_ids(store, UUID(base.slice_id), UUID(base.mapping_id))
    card = load_card(store, base.card.weights_sha256)
    estimator = build_estimator(load_model_from_store(store, card.weights_sha256), device="cpu")
    spec = get_spec(load_catalog(), name=name)
    target = uuid4()
    env = Environment(
        compute_target_id=target, gpu_model=None, cuda_version=None, driver_version=None
    )
    profile = calibrate(
        loader=loader, estimator=estimator, perturbation=build_any_perturbation(spec, estimator),
        level=level, seed=0, device="cpu", compute_target_id=target, model_version_id=card.id,
        attack_spec_id=spec.id, environment=env, now=datetime(2026, 10, 1, tzinfo=UTC),
    )  # fmt: skip
    assert profile.sec_per_image > 0 and profile.attack_spec_id == spec.id


def test_patch_calibration_measures_evaluation_and_training(base: Base) -> None:
    """Phase 6: `adv_patch` đo đánh giá bằng patch ngẫu nhiên, train bằng vài vòng RobustDPatch."""
    store = LocalStore(base.root)
    loader = SliceLoader.from_ids(store, UUID(base.slice_id), UUID(base.mapping_id))
    card = load_card(store, base.card.weights_sha256)
    estimator = build_estimator(load_model_from_store(store, card.weights_sha256), device="cpu")
    spec = get_spec(load_catalog(), name="adv_patch")
    perturbation = calibration_patch(spec, loader, estimator)
    assert cast(Any, perturbation).area_ratio == spec.primary_param.max
    image, target, _, info = loader.load(loader.slice.image_ids[0])
    out = perturbation.apply(
        image[None], [{**target, "image_id": "x"}], spec.primary_param.max, 0,
        letterbox_mask([info]),
    )  # fmt: skip
    assert out.shape == image[None].shape and (out != image[None]).any()
    assert patch_training_cost(spec, loader, estimator) > 0
