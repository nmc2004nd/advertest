"""Làm mờ trong luồng failure case của worker (validation.md Phase 6, mục Làm mờ; plan task 23).

Fixture `setup`, `straight` lấy từ `conftest.py`.
"""

from __future__ import annotations

import io
from typing import Any

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from ml_core.privacy import METHOD, VERSION
from ml_core.privacy.blur import blur_regions, region_mask
from ml_core.privacy.case import case_regions
from ml_core.runner.candidates import StoreCandidates
from ml_core.runner.executor import FinalizedRun, RunExecutor
from ml_core.runner.images import amplified_perturbation, letterbox_mask, png_bytes, thumbnail_webp
from ml_core.runner.tests.test_executor import RUN_ID, MemStore, _executor, _run_all


def _decode(data: bytes) -> NDArray[np.uint8]:
    return np.asarray(Image.open(io.BytesIO(data)).convert("RGB"))


def _regions(setup: dict[str, Any], image_id: str) -> list[tuple[float, float, float, float]]:
    """Vùng làm mờ tính lại từ dữ liệu gốc (dataset, prediction), như executor."""
    image, target, ignore, _ = setup["runner"].loader.load(image_id)
    attacked = setup["estimator"].predict(image[None], batch_size=1)[0]
    context = setup["context"]
    return case_regions(
        ground_truth=target,
        clean=context.clean_predictions[image_id],
        attacked=attacked,
        ignore_boxes=ignore["boxes"],
        class_names=context.class_names,
        width=image.shape[2],
        height=image.shape[1],
    )


def test_every_new_case_is_anonymized(straight: tuple[FinalizedRun, MemStore]) -> None:
    finalized, _ = straight
    assert finalized.failure_cases
    for record in finalized.failure_cases:
        assert record.anonymization is not None
        assert record.anonymization.applied
        assert (record.anonymization.method, record.anonymization.version) == (METHOD, VERSION)
        assert record.anonymization.regions_count > 0


def _unblurred(setup: dict[str, Any], image_id: str) -> dict[str, NDArray[np.float32]]:
    """Ảnh hiển thị chưa làm mờ, tái tạo từ dataset và perturbation (FGSM tất định từng ảnh)."""
    image, target, _, info = setup["runner"].loader.load(image_id)
    adversarial = setup["perturbation"].apply(
        image[None], [target], 8.0, 0, letterbox_mask([info])
    )[0]
    return {
        "clean": image,
        "adversarial": adversarial,
        "perturbation": amplified_perturbation(image, adversarial, setup["eps"]),
    }


def test_stored_display_images_are_exactly_the_blurred_versions(
    setup: dict[str, Any], straight: tuple[FinalizedRun, MemStore]
) -> None:
    """Mọi ảnh hiển thị (3 PNG, 2 thumbnail) trùng đúng bản làm mờ của ảnh tái tạo từ dataset,
    nên không file nào là bản chưa làm mờ; ngoài vùng làm mờ giống hệt ảnh gốc.

    Ảnh của fixture là các mảng màu phẳng nên làm mờ có thể không đổi pixel nào; việc làm mờ có
    thay đổi ảnh có chi tiết được kiểm tra ở `test_blur.py`.
    """
    finalized, store = straight
    for record in finalized.failure_cases:
        raw = _unblurred(setup, record.image_id)
        regions = _regions(setup, record.image_id)
        assert regions
        blurred = {name: blur_regions(image, regions) for name, image in raw.items()}
        height, width = raw["clean"].shape[1:]
        outside = ~region_mask(regions, width, height)
        artifacts = record.artifacts
        for name, key in (
            ("clean", artifacts.clean_png),
            ("adversarial", artifacts.adversarial_png),
            ("perturbation", artifacts.perturbation_png),
        ):
            stored = _decode(store.get(key))
            np.testing.assert_array_equal(stored, _decode(png_bytes(blurred[name])), key)
            np.testing.assert_array_equal(
                stored[outside], _decode(png_bytes(raw[name]))[outside], key
            )
        for name, thumb in (
            ("clean", artifacts.clean_thumb),
            ("adversarial", artifacts.adversarial_thumb),
        ):
            assert thumb is not None
            assert store.get(thumb) == thumbnail_webp(blurred[name]), thumb


class _NoBlur(StoreCandidates):
    """Ứng viên không làm mờ (chỉ để so metric)."""

    def add(self, image_id: str, clean: Any, adversarial: Any, regions: Any) -> None:
        super().add(image_id, clean, adversarial, [])


def test_metrics_do_not_depend_on_blurring(
    setup: dict[str, Any], straight: tuple[FinalizedRun, MemStore]
) -> None:
    finalized, _ = straight
    store = MemStore()
    executor = _executor(setup, store, candidates=_NoBlur(store, f"runs/{RUN_ID}", setup["eps"]))
    _run_all(executor, setup, 3)
    unblurred = executor.finalize(RUN_ID)
    assert unblurred.metrics == finalized.metrics
    assert [r.image_id for r in unblurred.failure_cases] == [
        r.image_id for r in finalized.failure_cases
    ]


def test_old_checkpoint_without_blur_info_is_not_marked_anonymized(setup: dict[str, Any]) -> None:
    store = MemStore()
    executor = _executor(setup, store)
    _run_all(executor, setup, 3)
    checkpoint = executor.to_checkpoint()
    for inputs in checkpoint["case_inputs"].values():
        inputs.pop("blur_regions")  # checkpoint trước Phase 6
    resumed = RunExecutor.from_checkpoint(
        checkpoint,
        fingerprint=executor.fingerprint,
        level=executor.level,
        seed=executor.seed,
        perturbation=executor.perturbation,
        estimator=executor.estimator,
        context=executor.context,
        candidates=executor.candidates,
    )
    cases = resumed.finalize(RUN_ID).failure_cases
    assert cases and all(record.anonymization is None for record in cases)
