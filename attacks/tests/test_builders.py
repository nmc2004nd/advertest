"""Registry perturbation (plan.md Phase R1, task 10)."""

from typing import Any, ClassVar

import numpy as np
import pytest

from advertest_contracts.enums import PerturbationImageKind
from advertest_contracts.models import AttackSpec
from advertest_contracts.perturbation import ImageBatch, MaskBatch, Perturbation
from attacks.art_adapter import ArtPerturbation
from attacks.builders import (
    DEFAULT_REGISTRY,
    BuildContext,
    IncompatibleAttack,
    PerturbationRegistry,
    UnsupportedAttack,
)
from attacks.patch.adapter import PatchPerturbation
from attacks.tests import fake_detector as fd
from attacks.tests.transform_helpers import letterbox_batch, spec, targets


class _Identity:
    def __init__(self, spec: AttackSpec) -> None:
        self.spec = spec

    def apply(
        self,
        images: ImageBatch,
        targets: list[dict[str, Any]],
        level: float,
        seed: int,
        mask: MaskBatch | None = None,
    ) -> ImageBatch:
        return images * np.float32(1)


class _IdentityBuilder:
    adapter: ClassVar[str] = "test.identity"
    requires: ClassVar[frozenset[str]] = frozenset()
    image_kind: ClassVar[PerturbationImageKind] = PerturbationImageKind.DIFFERENCE

    def build(self, spec: AttackSpec, ctx: BuildContext) -> Perturbation:
        return _Identity(spec)

    def linf_eps(self, spec: AttackSpec, level: float) -> float | None:
        return None


class _NeedsGradients(_IdentityBuilder):
    adapter: ClassVar[str] = "test.gradients"
    requires: ClassVar[frozenset[str]] = frozenset({"gradients"})


def test_fake_builder_registers_and_builds() -> None:
    registry = PerturbationRegistry(resolver=lambda _spec: "test.identity")
    registry.register(_IdentityBuilder())
    perturbation = registry.build(spec("fgsm"), BuildContext(estimator=None))
    images, mask = letterbox_batch(2)
    out = perturbation.apply(images, targets(2), 1, 0, mask)
    np.testing.assert_array_equal(out, images)


def test_duplicate_adapter_rejected() -> None:
    registry = PerturbationRegistry()
    registry.register(_IdentityBuilder())
    with pytest.raises(ValueError, match=r"test\.identity"):
        registry.register(_IdentityBuilder())


def test_gradient_builder_without_estimator_is_incompatible() -> None:
    registry = PerturbationRegistry(resolver=lambda _spec: "test.gradients")
    registry.register(_NeedsGradients())
    with pytest.raises(IncompatibleAttack, match="fgsm cần gradient"):
        registry.build(spec("fgsm"), BuildContext(estimator=None))


@pytest.mark.parametrize("name", ["fgsm", "pgd_linf", "pgd_l2", "adv_patch"])
def test_default_white_box_without_estimator_is_incompatible(name: str) -> None:
    with pytest.raises(
        IncompatibleAttack, match=f"^{name} cần gradient nhưng model không hỗ trợ gradient$"
    ):
        DEFAULT_REGISTRY.build(spec(name), BuildContext(estimator=None))


def test_unknown_adapter_lists_registered() -> None:
    registry = PerturbationRegistry(resolver=lambda _spec: "test.missing")
    registry.register(_IdentityBuilder())
    with pytest.raises(UnsupportedAttack, match=r"test\.missing.*test\.identity"):
        registry.builder_for(spec("fog"))


def test_unknown_art_class_keeps_art_message() -> None:
    fgsm = spec("fgsm").model_copy(update={"art_class": "CarliniL2Method"})
    with pytest.raises(UnsupportedAttack, match="art_class 'CarliniL2Method' chưa được hỗ trợ"):
        DEFAULT_REGISTRY.build(fgsm, BuildContext(estimator=fd.estimator()))


# Như `ml_core/runner/images.py::perturbation_kind` và `executor.py::linf_eps` trước R1.
@pytest.mark.parametrize(
    ("name", "kind", "eps"),
    [
        ("fgsm", PerturbationImageKind.AMPLIFIED_NOISE, 8 / 255),
        ("pgd_linf", PerturbationImageKind.AMPLIFIED_NOISE, 8 / 255),
        ("pgd_l2", PerturbationImageKind.AMPLIFIED_NOISE, None),
        ("fog", PerturbationImageKind.DIFFERENCE, None),
        ("bbox_occlusion", PerturbationImageKind.DIFFERENCE, None),
        ("adv_patch", PerturbationImageKind.PATCH_LOCATION, None),
    ],
)
def test_image_kind_and_linf_eps(name: str, kind: PerturbationImageKind, eps: float | None) -> None:
    builder = DEFAULT_REGISTRY.builder_for(spec(name))
    assert builder.image_kind == kind
    assert builder.linf_eps(spec(name), 8.0) == eps


def test_linf_eps_matches_art_perturbation() -> None:
    perturbation = ArtPerturbation(spec("pgd_linf"), fd.estimator())
    builder = DEFAULT_REGISTRY.builder_for(spec("pgd_linf"))
    assert builder.linf_eps(spec("pgd_linf"), 4.0) == perturbation.eps(4.0)


def test_patch_builder_uses_trained_patch() -> None:
    patch = np.full((3, 8, 8), 0.5, dtype=np.float32)
    ctx = BuildContext(estimator=fd.estimator(), patch=patch, area_ratio=0.05)
    perturbation = DEFAULT_REGISTRY.build(spec("adv_patch"), ctx)
    assert isinstance(perturbation, PatchPerturbation)
    assert perturbation.patch is patch
    assert perturbation.area_ratio == 0.05


def test_patch_builder_needs_patch() -> None:
    with pytest.raises(ValueError, match="patch đã train"):
        DEFAULT_REGISTRY.build(spec("adv_patch"), BuildContext(estimator=fd.estimator()))
