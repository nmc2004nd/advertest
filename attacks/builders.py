"""Registry perturbation (requirements.md Phase R1, `### Registry`; plan.md bước 8).

Mỗi loại phép biến đổi là một builder đăng ký theo tên adapter. R1 chưa có trường `adapter` trong
contract nên tên adapter được suy ra từ `kind` và `art_class` (`effective_adapter`); registry nhận
`resolver` tiêm vào được để test chọn builder giả.

Phase R2 (plan.md bước 10): resolver mặc định là `adapter_of`, đọc `spec.adapter` trước rồi mới tới
`effective_adapter`. Builder khai báo `kind` và `params_schema` (JSON Schema của `fixed_params`) để
`validate` kiểm spec mới và `adapters()` liệt kê cho `GET /attack-adapters`. Builder thiếu hai thuộc
tính này (builder giả của test R1) vẫn đăng ký và dựng được, nhưng không được liệt kê và không bị
kiểm `fixed_params`.

`UnsupportedAttack` và `IncompatibleAttack` được export lại ở đây để worker chỉ import
`attacks.builders` và `attacks.registry`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, ClassVar, Protocol

from art.estimators.estimator import BaseEstimator

from advertest_contracts.enums import AttackKind, PerturbationImageKind
from advertest_contracts.models import AttackAdapterInfo, AttackSpec
from advertest_contracts.perturbation import Perturbation
from attacks.art_adapter import IncompatibleAttack, UnsupportedAttack, level_to_eps
from attacks.art_adapter import build_perturbation as build_art_perturbation
from attacks.common.params_schema import SchemaError, schema_errors
from attacks.corruptions.adapter import CorruptionPerturbation
from attacks.corruptions.functions import NAMES as CORRUPTION_NAMES
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
    "InvalidSpec",
    "OcclusionBuilder",
    "PatchBuilder",
    "PerturbationBuilder",
    "PerturbationRegistry",
    "UnsupportedAttack",
    "adapter_of",
    "effective_adapter",
]

GRADIENTS = "gradients"
_PATCH_ART_CLASS = "RobustDPatch"


class InvalidSpec(ValueError):
    """Spec không dùng được với registry: adapter lạ, sai `kind` hay `fixed_params` sai schema."""


@dataclass(frozen=True)
class BuildContext:
    estimator: BaseEstimator | None  # None khi model không hỗ trợ gradient
    patch: PatchArray | None = None  # patch đã train, chỉ với patch.*
    area_ratio: float | None = None  # area_ratio mà patch được train, chỉ với patch.*


class PerturbationBuilder(Protocol):
    """`kind: ClassVar[AttackKind]`, `params_schema: ClassVar[dict]` là tùy chọn (xem đầu file)."""

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
    kind: ClassVar[AttackKind] = AttackKind.ATTACK
    # Khóa ngoài `eps_step_ratio` được truyền thẳng cho lớp ART (`art_adapter._build_attack`).
    params_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "norm": {"enum": ["inf", 2]},
            "max_iter": {"type": "integer", "minimum": 1},
            "eps_step_ratio": {"type": "number", "exclusiveMinimum": 0},
            "num_random_init": {"type": "integer", "minimum": 0},
        },
        "required": ["norm"],
        "additionalProperties": False,
    }
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
    kind: ClassVar[AttackKind] = AttackKind.CORRUPTION
    params_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "corruption": {"enum": sorted(CORRUPTION_NAMES)},
            "applied_to": {"enum": ["image_region"]},
        },
        "required": ["corruption"],
        "additionalProperties": False,
    }
    requires: ClassVar[frozenset[str]] = frozenset()
    image_kind: ClassVar[PerturbationImageKind] = PerturbationImageKind.DIFFERENCE

    def build(self, spec: AttackSpec, ctx: BuildContext) -> Perturbation:
        return CorruptionPerturbation(spec)

    def linf_eps(self, spec: AttackSpec, level: float) -> float | None:
        return None


class OcclusionBuilder:
    adapter: ClassVar[str] = "occlusion.bbox"
    kind: ClassVar[AttackKind] = AttackKind.OCCLUSION
    params_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "shape": {"enum": ["box_aspect_rectangle"]},
            "placement": {"enum": ["random_inside_box"]},
            "fill_255": {"type": "integer", "minimum": 0, "maximum": 255},
        },
        "additionalProperties": False,
    }
    requires: ClassVar[frozenset[str]] = frozenset()
    image_kind: ClassVar[PerturbationImageKind] = PerturbationImageKind.DIFFERENCE

    def build(self, spec: AttackSpec, ctx: BuildContext) -> Perturbation:
        return OcclusionPerturbation(spec)

    def linf_eps(self, spec: AttackSpec, level: float) -> float | None:
        return None


class PatchBuilder:
    """Đánh giá patch đã train (`ctx.patch`); việc train patch vẫn ở worker."""

    adapter: ClassVar[str] = "patch.robust_dpatch"
    kind: ClassVar[AttackKind] = AttackKind.ATTACK
    params_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "shape": {"enum": ["square"]},
            "placement": {"enum": ["image_region_center"]},
            "brightness_range": {
                "type": "array",
                "items": {"type": "number", "minimum": 0},
                "minItems": 2,
                "maxItems": 2,
            },
        },
        "additionalProperties": False,
    }
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


def adapter_of(spec: AttackSpec) -> str:
    """Tên adapter của spec: `spec.adapter`, hoặc `effective_adapter` khi spec không ghi."""
    return spec.adapter if spec.adapter is not None else effective_adapter(spec)


class PerturbationRegistry:
    def __init__(self, resolver: Callable[[AttackSpec], str] = adapter_of) -> None:
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

    def validate(self, spec: AttackSpec) -> None:
        """Báo `InvalidSpec` khi adapter không có trong registry, khi `kind` của spec khác `kind`
        của builder, hoặc khi `fixed_params` sai `params_schema` (requirements.md Phase R2,
        Catalog attack)."""
        adapter = self.resolver(spec)
        builder = self._builders.get(adapter)
        if builder is None:
            raise InvalidSpec(
                f"{spec.name}: adapter {adapter!r} không có trong registry "
                f"(có: {', '.join(sorted(self._builders))})"
            )
        kind = getattr(builder, "kind", None)
        if kind is not None and spec.kind != kind:
            raise InvalidSpec(
                f"{spec.name}: adapter {adapter!r} dành cho kind = {kind}, "
                f"spec có kind = {spec.kind}"
            )
        schema = getattr(builder, "params_schema", None)
        if schema is not None:
            try:
                errors = schema_errors(spec.fixed_params, schema)
            except SchemaError as exc:
                raise InvalidSpec(f"{spec.name}: params_schema của {adapter!r} lỗi: {exc}") from exc
            if errors:
                raise InvalidSpec(f"{spec.name}: " + "; ".join(errors))

    def adapters(self) -> list[AttackAdapterInfo]:
        """Adapter cho `GET /attack-adapters`, sắp theo tên; bỏ builder thiếu `kind` hay
        `params_schema`."""
        infos: list[AttackAdapterInfo] = []
        for name in sorted(self._builders):
            builder = self._builders[name]
            kind = getattr(builder, "kind", None)
            schema = getattr(builder, "params_schema", None)
            if kind is None or schema is None:
                continue
            infos.append(
                AttackAdapterInfo(
                    name=name,
                    kind=kind,
                    params_schema=schema,
                    requires_gradients=GRADIENTS in builder.requires,
                )
            )
        return infos

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
