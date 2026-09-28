from typing import Any

import numpy as np
import pytest

from advertest_contracts.models import AttackSpec, compute_spec_sha256
from attacks.art_adapter import (
    ArtPerturbation,
    IncompatibleAttack,
    UnsupportedAttack,
    build_perturbation,
)
from attacks.registry import get_spec, load_catalog
from attacks.tests import fake_detector as fd

ATTACKS = [("fgsm", 8.0), ("pgd_linf", 8.0), ("pgd_l2", 2.0)]


@pytest.fixture(scope="module")
def estimator() -> Any:
    return fd.estimator()


def _perturbation(name: str, estimator: Any) -> ArtPerturbation:
    return build_perturbation(get_spec(load_catalog(), name=name), estimator)


def _real(mask: np.ndarray) -> np.ndarray:
    return np.broadcast_to(mask == 1, (mask.shape[0], 3, *mask.shape[2:]))


@pytest.mark.parametrize(("name", "level"), ATTACKS)
def test_perturbation_only_inside_mask_and_in_range(
    name: str, level: float, estimator: Any
) -> None:
    x, mask = fd.images(), fd.mask()
    adv = _perturbation(name, estimator).apply(x, fd.targets(), level, seed=0, mask=mask)
    assert adv.shape == x.shape and adv.dtype == np.float32
    delta = adv - x
    real = _real(mask)
    assert np.array_equal(adv[~real], x[~real]), "vùng pad phải giữ nguyên chính xác"
    assert np.abs(delta[real]).max() > 0, "phải có nhiễu trong vùng ảnh thật"
    assert adv.min() >= 0.0 and adv.max() <= 1.0


@pytest.mark.parametrize("name", ["fgsm", "pgd_linf"])
def test_linf_norm_bound(name: str, estimator: Any) -> None:
    x = fd.images()
    adv = _perturbation(name, estimator).apply(x, fd.targets(), 8, seed=0, mask=fd.mask())
    assert np.abs(adv - x).max() <= 8 / 255 + 1e-6


def test_fgsm_level_unit_is_1_over_255(estimator: Any) -> None:
    x = fd.images()
    adv = _perturbation("fgsm", estimator).apply(x, fd.targets(), 8, seed=0, mask=fd.mask())
    # Điểm ảnh không bị clip đi đúng một bước eps.
    assert np.isclose(np.abs(adv - x).max(), 8 / 255, atol=1e-6)


def test_l2_norm_bound_per_image(estimator: Any) -> None:
    x = fd.images()
    adv = _perturbation("pgd_l2", estimator).apply(x, fd.targets(), 2, seed=0, mask=fd.mask())
    norms = np.linalg.norm((adv - x).reshape(len(x), -1), axis=1)
    assert (norms <= 2 + 1e-4).all()
    assert (norms > 1.0).all()


@pytest.mark.parametrize(("name", "level"), ATTACKS)
def test_level_zero_returns_copy(name: str, level: float, estimator: Any) -> None:
    x = fd.images()
    adv = _perturbation(name, estimator).apply(x, fd.targets(), 0, seed=0, mask=fd.mask())
    assert np.array_equal(adv, x)
    assert adv is not x


def test_mask_none_perturbs_whole_image(estimator: Any) -> None:
    x = fd.images()
    adv = _perturbation("pgd_linf", estimator).apply(x, fd.targets(), 8, seed=0)
    pad = ~_real(fd.mask())
    assert np.abs(adv - x)[pad].max() > 0


@pytest.mark.parametrize(("name", "level"), ATTACKS)
def test_deterministic_and_independent_of_batch_size(
    name: str, level: float, estimator: Any
) -> None:
    x, mask, targets = fd.images(), fd.mask(), fd.targets()
    perturbation = _perturbation(name, estimator)
    full = perturbation.apply(x, targets, level, seed=3, mask=mask)
    again = perturbation.apply(x, targets, level, seed=3, mask=mask)
    assert np.array_equal(full, again)
    single = np.concatenate(
        [
            perturbation.apply(
                x[i : i + 1], targets[i : i + 1], level, seed=3, mask=mask[i : i + 1]
            )
            for i in range(len(x))
        ]
    )
    np.testing.assert_allclose(single, full, atol=1e-6)


def test_uses_ground_truth_targets(estimator: Any) -> None:
    # Loss của model giả nhân theo số box: đổi targets thì gradient (và PGD) đổi theo.
    x, mask = fd.images(), fd.mask()
    perturbation = _perturbation("pgd_l2", estimator)
    with_boxes = perturbation.apply(x, fd.targets(), 2, seed=0, mask=mask)
    no_boxes = [{"boxes": np.zeros((0, 4), np.float32), "labels": np.zeros(0, np.int64)}] * len(x)
    without = perturbation.apply(x, no_boxes, 2, seed=0, mask=mask)
    assert not np.array_equal(with_boxes, without)


def test_rejects_bad_inputs(estimator: Any) -> None:
    perturbation = _perturbation("pgd_linf", estimator)
    x, targets = fd.images(), fd.targets()
    with pytest.raises(ValueError, match="ngoài dải"):
        perturbation.apply(x, targets, 33, seed=0)
    with pytest.raises(ValueError, match="ngoài dải"):
        perturbation.apply(x, targets, -1, seed=0)
    with pytest.raises(ValueError, match="mask"):
        perturbation.apply(x, targets, 4, seed=0, mask=np.ones((5, 3, 64, 64), np.float32))
    with pytest.raises(ValueError, match="targets"):
        perturbation.apply(x, targets[:2], 4, seed=0)
    with pytest.raises(ValueError, match="float32"):
        perturbation.apply(x.astype(np.float64), targets, 4, seed=0)


def test_eps_conversion(estimator: Any) -> None:
    assert _perturbation("pgd_linf", estimator).eps(8) == pytest.approx(8 / 255)
    assert _perturbation("pgd_l2", estimator).eps(2) == 2


class _NoGradients:
    """Estimator chỉ predict, không có `loss_gradient` (không phải `LossGradientsMixin`)."""

    clip_values = (0.0, 1.0)

    def predict(self, x: np.ndarray, **kwargs: Any) -> Any:
        return x


def test_incompatible_when_estimator_has_no_gradients() -> None:
    spec = get_spec(load_catalog(), name="fgsm")
    with pytest.raises(IncompatibleAttack, match="fgsm"):
        build_perturbation(spec, _NoGradients())


def _spec(**overrides: Any) -> AttackSpec:
    body = get_spec(load_catalog(), name="pgd_linf").model_dump(
        mode="json", exclude={"id", "spec_sha256"}
    )
    body.update(overrides)
    return AttackSpec.model_validate(
        {
            **body,
            "id": "00000000-0000-5000-8000-000000000009",
            "spec_sha256": compute_spec_sha256(body),
        }
    )


def test_unsupported_specs(estimator: Any) -> None:
    with pytest.raises(UnsupportedAttack, match="art_class"):
        build_perturbation(_spec(art_class="CarliniL2Method"), estimator)
    with pytest.raises(UnsupportedAttack, match="kind"):
        build_perturbation(
            _spec(kind="corruption", art_class=None, requires_gradients=False), estimator
        )
    primary = {"name": "eps", "type": "continuous", "min": 0, "max": 1, "unit": "ratio"}
    with pytest.raises(UnsupportedAttack, match="đơn vị"):
        build_perturbation(_spec(primary_param=primary), estimator)
