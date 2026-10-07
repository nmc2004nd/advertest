"""Hàm dựng Perturbation cho cả catalog (plan.md Phase 6, task 10)."""

import numpy as np
import pytest

from advertest_contracts.perturbation import Perturbation
from attacks.art_adapter import ArtPerturbation, IncompatibleAttack
from attacks.corruptions.adapter import CorruptionPerturbation
from attacks.factory import build_perturbation
from attacks.occlusion.adapter import OcclusionPerturbation
from attacks.tests import fake_detector as fd
from attacks.tests.transform_helpers import letterbox_batch, spec, targets

CORRUPTIONS = ["fog", "snow", "frost", "motion_blur", "contrast"]


def _satisfies_protocol(perturbation: Perturbation) -> Perturbation:
    """mypy kiểm tra adapter cài đúng `Perturbation` (Protocol không runtime_checkable)."""
    return perturbation


@pytest.mark.parametrize("name", CORRUPTIONS)
def test_corruptions_without_estimator(name: str) -> None:
    perturbation = build_perturbation(spec(name), None)
    assert isinstance(perturbation, CorruptionPerturbation)
    _satisfies_protocol(perturbation)


def test_occlusion_without_estimator() -> None:
    perturbation = build_perturbation(spec("bbox_occlusion"), None)
    assert isinstance(perturbation, OcclusionPerturbation)
    _satisfies_protocol(perturbation)
    images, mask = letterbox_batch(1)
    out = perturbation.apply(images, targets(1, [[[10.0, 230.0, 90.0, 300.0]]]), 0.5, 0, mask)
    assert out.shape == images.shape


def test_attacks_go_to_art_adapter() -> None:
    assert isinstance(build_perturbation(spec("fgsm"), fd.estimator()), ArtPerturbation)
    with pytest.raises(IncompatibleAttack, match="không hỗ trợ gradient"):
        build_perturbation(spec("pgd_linf"), None)


def test_patch_needs_trained_patch() -> None:
    # Patch đã train chỉ truyền được qua `BuildContext` của registry (Phase R1).
    with pytest.raises(ValueError, match="patch đã train"):
        build_perturbation(spec("adv_patch"), fd.estimator())


def test_corruption_output_is_float32() -> None:
    images, mask = letterbox_batch(1)
    out = build_perturbation(spec("fog"), None).apply(images, targets(1), 1, 0, mask)
    assert out.dtype == np.float32
