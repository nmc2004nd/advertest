import numpy as np
import pytest

from attacks.common.seed import image_rng, per_image_seed, target_image_id


def test_per_image_seed_is_stable_and_depends_on_both_inputs() -> None:
    assert per_image_seed(0, "000123") == per_image_seed(0, "000123")
    assert per_image_seed(0, "000123") != per_image_seed(0, "000124")
    assert per_image_seed(0, "000123") != per_image_seed(1, "000123")
    assert 0 <= per_image_seed(7, "a") < 2**64


def test_image_rng_reproducible() -> None:
    a = image_rng(3, "x").random(4)
    b = image_rng(3, "x").random(4)
    np.testing.assert_array_equal(a, b)
    assert not np.array_equal(a, image_rng(3, "y").random(4))


def test_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="không âm"):
        per_image_seed(-1, "x")
    with pytest.raises(ValueError, match="rỗng"):
        per_image_seed(0, "")
    with pytest.raises(ValueError, match="image_id"):
        target_image_id({"boxes": []}, 2)
    assert target_image_id({"image_id": "k"}, 0) == "k"
