"""Registry perturbation, phần thuần (validation.md Phase R1, `### Registry`; plan.md bước 7,
"trước Group 3"). Không cần DB, không cần model.

- Catalog → adapter: mọi spec của catalog có `effective_adapter` thuộc 4 adapter mặc định, khớp
  builder của `DEFAULT_REGISTRY`; `spec_sha256` không đổi so với
  `contracts/seeds/attack_specs.json`.
- Đăng ký trùng tên adapter → lỗi, registry giữ builder đã đăng ký trước.
- Không có adapter → `UnsupportedAttack` (export lại từ `attacks.builders`).

Phần tích hợp qua runner (builder giả `test.identity` qua `perturbation_factory`, `ModelProvider`
giả) được thêm trước Group 5.
"""

from __future__ import annotations

import json
from typing import Any, ClassVar

import pytest

from advertest_contracts.enums import PerturbationImageKind
from advertest_contracts.models import AttackSpec, compute_spec_sha256
from attacks.builders import (
    DEFAULT_REGISTRY,
    BuildContext,
    PerturbationRegistry,
    UnsupportedAttack,
    effective_adapter,
)
from attacks.registry import SEED_FILE, get_spec, load_catalog

DEFAULT_ADAPTERS = {
    "art.evasion",
    "corruption.imagecorruptions",
    "occlusion.bbox",
    "patch.robust_dpatch",
}

# (kind, art_class) của catalog → adapter (requirements.md Phase R1, `## Data / Fields`).
EXPECTED_ADAPTER = {
    "fgsm": "art.evasion",
    "pgd_linf": "art.evasion",
    "pgd_l2": "art.evasion",
    "fog": "corruption.imagecorruptions",
    "snow": "corruption.imagecorruptions",
    "frost": "corruption.imagecorruptions",
    "motion_blur": "corruption.imagecorruptions",
    "contrast": "corruption.imagecorruptions",
    "bbox_occlusion": "occlusion.bbox",
    "adv_patch": "patch.robust_dpatch",
}


class _FakeBuilder:
    """Builder giả tối thiểu cho registry; không bao giờ được dựng thật trong file này."""

    adapter: ClassVar[str] = "test.identity"
    requires: ClassVar[frozenset[str]] = frozenset()
    image_kind: ClassVar[PerturbationImageKind] = PerturbationImageKind.DIFFERENCE

    def build(self, spec: AttackSpec, ctx: BuildContext) -> Any:
        raise AssertionError("test thuần registry không dựng perturbation")

    def linf_eps(self, spec: AttackSpec, level: float) -> float | None:
        return None


class _OtherFakeBuilder(_FakeBuilder):
    """Cùng tên adapter với `_FakeBuilder`, khác lớp."""


def _seed_hashes() -> dict[str, str]:
    return {item["name"]: item["spec_sha256"] for item in json.loads(SEED_FILE.read_text())}


def test_catalog_maps_to_default_adapters() -> None:
    catalog = load_catalog()
    assert {spec.name for spec in catalog} == set(EXPECTED_ADAPTER)

    used = set()
    for spec in catalog:
        adapter = effective_adapter(spec)
        assert adapter in DEFAULT_ADAPTERS, spec.name
        assert adapter == EXPECTED_ADAPTER[spec.name], spec.name
        builder = DEFAULT_REGISTRY.builder_for(spec)
        assert builder.adapter == adapter, spec.name
        used.add(adapter)
    assert used == DEFAULT_ADAPTERS


def test_spec_sha256_unchanged() -> None:
    seeds = _seed_hashes()
    catalog = load_catalog()
    assert len(catalog) == len(seeds) == 10
    for spec in catalog:
        before = spec.model_dump(mode="json")
        effective_adapter(spec)
        DEFAULT_REGISTRY.builder_for(spec)
        assert spec.model_dump(mode="json") == before, spec.name
        assert spec.spec_sha256 == seeds[spec.name], spec.name
        assert compute_spec_sha256(spec) == seeds[spec.name], spec.name


def test_duplicate_adapter_name_rejected() -> None:
    spec = get_spec(load_catalog(), name="fog")
    registry = PerturbationRegistry(resolver=lambda _spec: "test.identity")
    first = _FakeBuilder()
    registry.register(first)
    assert registry.builder_for(spec) is first

    with pytest.raises(Exception) as excinfo:  # spec chỉ nói "lỗi", không chốt kiểu
        registry.register(_OtherFakeBuilder())
    assert not isinstance(excinfo.value, AssertionError)
    assert registry.builder_for(spec) is first


def test_duplicate_of_default_adapter_name_rejected() -> None:
    catalog = load_catalog()
    registry = PerturbationRegistry()
    defaults = {
        DEFAULT_REGISTRY.builder_for(spec).adapter: DEFAULT_REGISTRY.builder_for(spec)
        for spec in catalog
    }
    for builder in defaults.values():
        registry.register(builder)

    clone = type("ArtClone", (_FakeBuilder,), {"adapter": "art.evasion"})()
    with pytest.raises(Exception) as excinfo:
        registry.register(clone)
    assert not isinstance(excinfo.value, AssertionError)
    fgsm = get_spec(catalog, name="fgsm")
    assert registry.builder_for(fgsm) is defaults["art.evasion"]


def test_unknown_adapter_is_unsupported() -> None:
    spec = get_spec(load_catalog(), name="fgsm")
    registry = PerturbationRegistry(resolver=lambda _spec: "test.missing")
    registry.register(_FakeBuilder())
    with pytest.raises(UnsupportedAttack):
        registry.builder_for(spec)
