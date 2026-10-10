"""validation.md Phase R3, Group 2 — `attacks.selfcheck.fixture_inputs` (`test_fixture_inputs.py`).
Không cần DB; dùng fixture KITTI và YOLOv8n trong `tests/fixtures/`.

Interface (requirements.md Phase R3, Chốt ở Group 0):
`fixture_inputs(*, with_estimator: bool, fixtures_dir: Path | None = None) -> SelfcheckInputs`,
`fixtures_dir = None` nghĩa là `ml_core.fixtures.FIXTURES_DIR`.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from ml_core.fixtures import FIXTURES_DIR


def _fixture_inputs(**kwargs: Any) -> Any:
    from attacks.selfcheck import (  # type: ignore[attr-defined,unused-ignore]
        fixture_inputs,  # Group 2
    )

    return fixture_inputs(**kwargs)


@pytest.fixture(scope="module")
def plain() -> Any:
    return _fixture_inputs(with_estimator=False)


def test_four_letterbox_images(plain: Any) -> None:
    assert plain.images.shape == (4, 3, 640, 640) and plain.images.dtype == np.float32
    assert float(plain.images.min()) >= 0.0 and float(plain.images.max()) <= 1.0
    assert plain.masks.shape == (4, 1, 640, 640)
    assert set(np.unique(plain.masks).tolist()) <= {0.0, 1.0}
    assert len(plain.targets) == 4
    assert plain.estimator is None


def test_with_estimator_same_images(plain: Any) -> None:
    full = _fixture_inputs(with_estimator=True, fixtures_dir=FIXTURES_DIR)
    assert full.estimator is not None
    np.testing.assert_array_equal(full.images, plain.images)
    np.testing.assert_array_equal(full.masks, plain.masks)
    assert [t["image_id"] for t in full.targets] == [t["image_id"] for t in plain.targets]
