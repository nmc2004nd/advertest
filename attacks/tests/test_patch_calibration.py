"""Đo sec_per_image_iteration (validation.md Phase 6, mục Ước lượng)."""

import pytest

from attacks.patch.calibration import measure_sec_per_image_iteration
from attacks.tests import fake_detector as fd
from attacks.tests.transform_helpers import spec


def test_measures_positive_seconds() -> None:
    value = measure_sec_per_image_iteration(
        spec("adv_patch"), fd.estimator(), fd.images(3), fd.mask(3), batch_size=2, iterations=2
    )
    assert value > 0


def test_rejects_empty_input() -> None:
    with pytest.raises(ValueError, match="ít nhất"):
        measure_sec_per_image_iteration(
            spec("adv_patch"), fd.estimator(), fd.images(1), fd.mask(1), batch_size=1, iterations=0
        )
