"""validation.md Phase R2, Group 2 — Adapter attack (`test_adapter_field.py`). Không cần DB.

- Spec có `adapter` khác `effective_adapter` thì registry chọn theo `adapter`; spec seed (không có
  `adapter`) giữ builder cũ.
- `fixed_params` sai `params_schema` → lỗi kiểm tra (`InvalidSpec`).
- `adapters()` liệt kê đúng 4 adapter mặc định cho `GET /attack-adapters`.

Interface (requirements.md Phase R2, Chốt ở Group 0, "Interface cho test nghiệm thu"):
`attacks.builders.adapter_of`, `InvalidSpec`, `PerturbationRegistry.validate`,
`PerturbationRegistry.adapters`.
"""

from __future__ import annotations

from typing import Any, ClassVar

import numpy as np
import pytest

from advertest_contracts.enums import AttackKind, PerturbationImageKind
from advertest_contracts.ids import content_id
from advertest_contracts.models import AttackAdapterInfo, AttackSpec, AttackSpecBody
from advertest_contracts.models import compute_spec_sha256 as sha
from attacks import builders
from attacks.builders import (
    DEFAULT_REGISTRY,
    BuildContext,
    PerturbationRegistry,
    effective_adapter,
)
from attacks.registry import load_catalog

DEFAULT_ADAPTERS = {
    "art.evasion": (AttackKind.ATTACK, True),
    "corruption.imagecorruptions": (AttackKind.CORRUPTION, False),
    "occlusion.bbox": (AttackKind.OCCLUSION, False),
    "patch.robust_dpatch": (AttackKind.ATTACK, True),
}


def _spec(base_name: str, **changes: Any) -> AttackSpec:
    base = next(s for s in load_catalog() if s.name == base_name)
    body = base.model_dump(mode="json", include=set(AttackSpecBody.model_fields))
    body.update(changes)
    digest = sha(AttackSpecBody.model_validate(body))
    return AttackSpec.model_validate({**body, "id": str(content_id(digest)), "spec_sha256": digest})


class _Marker:
    """Perturbation giả: cộng một hằng số để phân biệt builder nào đã dựng."""

    def __init__(self, spec: AttackSpec, value: float) -> None:
        self.spec = spec
        self.value = value

    def apply(
        self,
        images: np.ndarray,
        targets: list[dict[str, Any]],
        level: float,
        seed: int,
        mask: np.ndarray | None = None,
    ) -> np.ndarray:
        return np.clip(images + self.value, 0.0, 1.0).astype(np.float32)


class _FakeCorruption:
    adapter: ClassVar[str] = "corruption.fake_fog"
    kind: ClassVar[AttackKind] = AttackKind.CORRUPTION
    requires: ClassVar[frozenset[str]] = frozenset()
    image_kind: ClassVar[PerturbationImageKind] = PerturbationImageKind.DIFFERENCE
    params_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {"corruption": {"enum": ["fog"]}},
        "required": ["corruption"],
        "additionalProperties": False,
    }

    def build(self, spec: AttackSpec, ctx: BuildContext) -> Any:
        return _Marker(spec, 0.5)

    def linf_eps(self, spec: AttackSpec, level: float) -> float | None:
        return None


def test_seed_specs_have_no_adapter_and_keep_builder() -> None:
    for spec in load_catalog():
        assert spec.adapter is None, spec.name
        assert builders.adapter_of(spec) == effective_adapter(spec), spec.name
        assert DEFAULT_REGISTRY.builder_for(spec).adapter == effective_adapter(spec), spec.name


def test_adapter_field_overrides_effective_adapter() -> None:
    registry = PerturbationRegistry()  # resolver mặc định đọc `spec.adapter` trước
    for builder in {DEFAULT_REGISTRY.builder_for(s) for s in load_catalog()}:
        registry.register(builder)
    fake = _FakeCorruption()
    registry.register(fake)

    fog = _spec("fog")
    variant = _spec("fog", name="fog_fake", adapter="corruption.fake_fog")
    assert effective_adapter(variant) == "corruption.imagecorruptions"
    assert builders.adapter_of(variant) == "corruption.fake_fog"
    assert registry.builder_for(variant) is fake
    assert registry.builder_for(fog).adapter == "corruption.imagecorruptions"

    images = np.zeros((1, 3, 8, 8), dtype=np.float32)
    out = registry.build(variant, BuildContext(estimator=None)).apply(images, [{}], 1.0, 0)
    assert np.allclose(out, 0.5)


def test_explicit_default_adapter_changes_hash_but_not_builder() -> None:
    """Ghi rõ `adapter` bằng giá trị suy ra: hash khác spec seed (là spec mới), builder giống."""
    fog = _spec("fog")
    explicit = _spec("fog", name="fog_explicit", adapter="corruption.imagecorruptions")
    assert explicit.spec_sha256 != fog.spec_sha256
    assert DEFAULT_REGISTRY.builder_for(explicit) is DEFAULT_REGISTRY.builder_for(fog)


def test_validate_accepts_seed_specs() -> None:
    for spec in load_catalog():
        DEFAULT_REGISTRY.validate(spec)


@pytest.mark.parametrize(
    ("name", "changes"),
    [
        # Corruption ngoài 5 hàm có sẵn (thêm hàm mới là việc qua repo, Out of Scope).
        ("fog", {"name": "noise", "fixed_params": {"corruption": "gaussian_noise"}}),
        ("fog", {"name": "fog_extra", "fixed_params": {"corruption": "fog", "khong_co": 1}}),
        ("fog", {"name": "fog_empty", "fixed_params": {}}),
        ("fgsm", {"name": "fgsm_bad", "fixed_params": {"norm": "inf", "eps_step_ratio": "x"}}),
    ],
)
def test_invalid_fixed_params_rejected(name: str, changes: dict[str, Any]) -> None:
    with pytest.raises(builders.InvalidSpec):
        DEFAULT_REGISTRY.validate(_spec(name, **changes))


def test_unknown_adapter_rejected() -> None:
    with pytest.raises(builders.InvalidSpec):
        DEFAULT_REGISTRY.validate(_spec("fog", name="fog_x", adapter="corruption.khong_co"))


def test_adapter_kind_mismatch_rejected() -> None:
    """Spec corruption trỏ tới adapter của attack white-box."""
    with pytest.raises(builders.InvalidSpec):
        DEFAULT_REGISTRY.validate(_spec("fog", name="fog_art", adapter="art.evasion"))


def test_invalid_spec_is_value_error() -> None:
    assert issubclass(builders.InvalidSpec, ValueError)


def test_adapters_lists_default_builders() -> None:
    infos = DEFAULT_REGISTRY.adapters()
    assert all(isinstance(info, AttackAdapterInfo) for info in infos)
    assert [info.name for info in infos] == sorted(DEFAULT_ADAPTERS)
    for info in infos:
        kind, gradients = DEFAULT_ADAPTERS[info.name]
        assert (info.kind, info.requires_gradients) == (kind, gradients), info.name
        assert info.params_schema.get("type") == "object", info.name


def test_params_schema_of_corruption_lists_five_functions() -> None:
    info = next(i for i in DEFAULT_REGISTRY.adapters() if i.name == "corruption.imagecorruptions")
    schema: Any = info.params_schema
    allowed = schema["properties"]["corruption"]["enum"]
    assert sorted(allowed) == ["contrast", "fog", "frost", "motion_blur", "snow"]
