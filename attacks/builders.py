"""Registry perturbation (requirements.md Phase R1, `### Registry`; plan.md bước 8).

Mỗi loại phép biến đổi là một builder đăng ký theo tên adapter. R1 chưa có trường `adapter` trong
contract nên tên adapter được suy ra từ `kind` và `art_class` (`effective_adapter`); registry nhận
`resolver` tiêm vào được để test chọn builder giả, R2 chỉ cần thay resolver.

`UnsupportedAttack` và `IncompatibleAttack` được export lại ở đây để worker chỉ import
`attacks.builders` và `attacks.registry`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import ClassVar, Protocol

from art.estimators.estimator import BaseEstimator

from advertest_contracts.enums import AttackKind, PerturbationImageKind
from advertest_contracts.models import AttackSpec
from advertest_contracts.perturbation import Perturbation
from attacks.art_adapter import IncompatibleAttack, UnsupportedAttack, level_to_eps
from attacks.art_adapter import build_perturbation as build_art_perturbation
from attacks.corruptions.adapter import CorruptionPerturbation
from attacks.occlusion.adapter import OcclusionPerturbation
from attacks.patch.adapter import PatchPerturbation
from attacks.patch.training import PatchArray

__all__ = [
    "DEFAULT_REGISTRY",
    "GRADIENTS",
    "ArtEvasionBuilder",
    "BuildContext",
    "CorruptionBuilder",
    "IncompatibleAttack",
    "OcclusionBuilder",
    "PatchBuilder",
    "PerturbationBuilder",
    "PerturbationRegistry",
    "UnsupportedAttack",
    "effective_adapter",
]

GRADIENTS = "gradients"
_PATCH_ART_CLASS = "RobustDPatch"


@dataclass(frozen=True)
class BuildContext:
    estimator: BaseEstimator | None  # None khi model không hỗ trợ gradient
    patch: PatchArray | None = None  # patch đã train, chỉ với patch.*
    area_ratio: float | None = None  # area_ratio mà patch được train, chỉ với patch.*


class PerturbationBuilder(Protocol):
    adapter: ClassVar[str]
    requires: ClassVar[frozenset[str]]  # {"gradients"} với attack white-box
    image_kind: ClassVar[PerturbationImageKind]  # nội dung ảnh thứ ba của failure case

    def build(self, spec: AttackSpec, ctx: BuildContext) -> Perturbation: ...

    def linf_eps(self, spec: AttackSpec, level: float) -> float | None:
        """eps L∞ trên ảnh [0, 1] để khuếch đại ảnh nhiễu; `None` khi không áp dụng."""
        ...


def _incompatible(spec: AttackSpec) -> IncompatibleAttack:
    # Thông điệp `skipped` như Phase 2 (runner kiểm `supports_gradients` trước khi dựng).
    return IncompatibleAttack(f"{spec.name} cần gradient nhưng model không hỗ trợ gradient")


class ArtEvasionBuilder:
    """FGSM, PGD của ART (`attacks.art_adapter`)."""

    adapter: ClassVar[str] = "art.evasion"
    requires: ClassVar[frozenset[str]] = frozenset({GRADIENTS})
    image_kind: ClassVar[PerturbationImageKind] = PerturbationImageKind.AMPLIFIED_NOISE

    def build(self, spec: AttackSpec, ctx: BuildContext) -> Perturbation:
        if ctx.estimator is None:
            raise _incompatible(spec)
        return build_art_perturbation(spec, ctx.estimator)

    def linf_eps(self, spec: AttackSpec, level: float) -> float | None:
        return level_to_eps(spec, level) if str(spec.fixed_params.get("norm")) == "inf" else None


class CorruptionBuilder:
    adapter: ClassVar[str] = "corruption.imagecorruptions"
    requires: ClassVar[frozenset[str]] = frozenset()
    image_kind: ClassVar[PerturbationImageKind] = PerturbationImageKind.DIFFERENCE

    def build(self, spec: AttackSpec, ctx: BuildContext) -> Perturbation:
        return CorruptionPerturbation(spec)

    def linf_eps(self, spec: AttackSpec, level: float) -> float | None:
        return None


class OcclusionBuilder:
    adapter: ClassVar[str] = "occlusion.bbox"
    requires: ClassVar[frozenset[str]] = frozenset()
    image_kind: ClassVar[PerturbationImageKind] = PerturbationImageKind.DIFFERENCE

    def build(self, spec: AttackSpec, ctx: BuildContext) -> Perturbation:
        return OcclusionPerturbation(spec)

    def linf_eps(self, spec: AttackSpec, level: float) -> float | None:
        return None


class PatchBuilder:
    """Đánh giá patch đã train (`ctx.patch`); việc train patch vẫn ở worker."""

    adapter: ClassVar[str] = "patch.robust_dpatch"
    requires: ClassVar[frozenset[str]] = frozenset({GRADIENTS})
    image_kind: ClassVar[PerturbationImageKind] = PerturbationImageKind.PATCH_LOCATION

    def build(self, spec: AttackSpec, ctx: BuildContext) -> Perturbation:
        if ctx.patch is None or ctx.area_ratio is None:
            raise ValueError(f"{spec.name}: cần patch đã train và area_ratio trong BuildContext")
        return PatchPerturbation(spec, ctx.patch, area_ratio=ctx.area_ratio)

    def linf_eps(self, spec: AttackSpec, level: float) -> float | None:
        return None


def effective_adapter(spec: AttackSpec) -> str:
    """Tên adapter của spec, chỉ đọc `kind` và `art_class` (không đổi `spec_sha256`).

    `art_class` lạ của `kind = attack` vẫn đi vào `art.evasion` để `ArtPerturbation` báo
    `UnsupportedAttack` với thông điệp như trước R1.
    """
    if spec.kind == AttackKind.CORRUPTION:
        return CorruptionBuilder.adapter
    if spec.kind == AttackKind.OCCLUSION:
        return OcclusionBuilder.adapter
    if spec.art_class == _PATCH_ART_CLASS:
        return PatchBuilder.adapter
    return ArtEvasionBuilder.adapter


class PerturbationRegistry:
    def __init__(self, resolver: Callable[[AttackSpec], str] = effective_adapter) -> None:
        self.resolver = resolver
        self._builders: dict[str, PerturbationBuilder] = {}

    def register(self, builder: PerturbationBuilder) -> None:
        """Đăng ký builder; tên adapter đã có thì báo `ValueError` và giữ builder cũ."""
        if builder.adapter in self._builders:
            raise ValueError(f"adapter {builder.adapter!r} đã được đăng ký")
        self._builders[builder.adapter] = builder

    def builder_for(self, spec: AttackSpec) -> PerturbationBuilder:
        adapter = self.resolver(spec)
        builder = self._builders.get(adapter)
        if builder is None:
            raise UnsupportedAttack(
                f"{spec.name}: adapter {adapter!r} chưa được hỗ trợ "
                f"(có: {', '.join(sorted(self._builders))})"
            )
        return builder

    def build(self, spec: AttackSpec, ctx: BuildContext) -> Perturbation:
        """`Perturbation` cho spec; builder cần gradient mà không có estimator thì báo
        `IncompatibleAttack` (run `skipped`, như Phase 2)."""
        builder = self.builder_for(spec)
        if GRADIENTS in builder.requires and ctx.estimator is None:
            raise _incompatible(spec)
        return builder.build(spec, ctx)


def _default_registry() -> PerturbationRegistry:
    registry = PerturbationRegistry()
    for builder in (ArtEvasionBuilder(), CorruptionBuilder(), OcclusionBuilder(), PatchBuilder()):
        registry.register(builder)
    return registry


DEFAULT_REGISTRY = _default_registry()
