"""Registry perturbation, phần thuần (validation.md Phase R1, `### Registry`; plan.md bước 7,
"trước Group 3"). Không cần DB, không cần model.

- Catalog → adapter: mọi spec của catalog có `effective_adapter` thuộc 4 adapter mặc định, khớp
  builder của `DEFAULT_REGISTRY`; `spec_sha256` không đổi so với
  `contracts/seeds/attack_specs.json`.
- Đăng ký trùng tên adapter → lỗi, registry giữ builder đã đăng ký trước.
- Không có adapter → `UnsupportedAttack` (export lại từ `attacks.builders`).

Phần tích hợp qua runner CLI (thêm trước Group 5), cần model và fixture KITTI, không cần DB:
- builder giả `test.identity` (nhân ảnh với 1) trong registry riêng có resolver riêng, truyền qua
  `perturbation_factory`: run `completed`, ảnh sau biến đổi y hệt ảnh gốc;
- `ModelProvider` giả (model không hỗ trợ gradient, seam `model_provider`): FGSM `skipped`
  (`incompatible`, thông điệp như Phase 2), fog `completed`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, ClassVar

import numpy as np
import pytest
from typer.testing import CliRunner

from advertest_contracts.enums import PerturbationImageKind
from advertest_contracts.models import (
    AttackSpec,
    InferenceParams,
    ModelCard,
    compute_spec_sha256,
)
from attacks.builders import (
    DEFAULT_REGISTRY,
    BuildContext,
    PerturbationRegistry,
    UnsupportedAttack,
    effective_adapter,
)
from attacks.registry import SEED_FILE, get_spec, load_catalog
from ml_core.cli import app
from ml_core.fixtures import FIXTURES_DIR
from ml_core.models.adapter import Capabilities, ModelProvider, NoGradients
from ml_core.runner.config import LocalRunConfig
from ml_core.runner.run import run_config
from ml_core.store import LocalStore

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


# ---------------------------------------------------------------- tích hợp qua runner CLI
# Thêm trước Group 5 (plan.md bước 7). Seam của runner: `perturbation_factory(spec, estimator)`,
# `model_provider` (có `get(card, params, device) -> ModelAdapter`).

KITTI_ROOT = FIXTURES_DIR / "kitti"
WEIGHTS = FIXTURES_DIR / "yolov8n.pt"


class _Identity:
    """Nhân ảnh với 1; ghi lại để kiểm ảnh sau biến đổi y hệt ảnh gốc."""

    def __init__(self, spec: AttackSpec) -> None:
        self.spec = spec
        self.calls = 0
        self.max_abs_diff = 0.0

    def apply(
        self,
        images: Any,
        targets: list[dict[str, Any]],
        level: float,
        seed: int,
        mask: Any = None,
    ) -> Any:
        out = images * np.float32(1.0)
        self.calls += 1
        assert out.shape == images.shape and out.dtype == images.dtype
        self.max_abs_diff = max(self.max_abs_diff, float(np.abs(out - images).max()))
        return out


class _IdentityBuilder:
    adapter: ClassVar[str] = "test.identity"
    requires: ClassVar[frozenset[str]] = frozenset()
    image_kind: ClassVar[PerturbationImageKind] = PerturbationImageKind.DIFFERENCE

    def __init__(self) -> None:
        self.built: list[_Identity] = []

    def build(self, spec: AttackSpec, ctx: BuildContext) -> Any:
        perturbation = _Identity(spec)
        self.built.append(perturbation)
        return perturbation

    def linf_eps(self, spec: AttackSpec, level: float) -> float | None:
        return None


class _NoGradientAdapter:
    """Adapter thật nhưng khai báo không hỗ trợ gradient."""

    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.card = inner.card
        self.capabilities = Capabilities(gradients=False)

    def class_names(self) -> list[str]:
        return list(self.inner.class_names())

    def predict(self, images: Any, batch_size: int | None = None) -> Any:
        return self.inner.predict(images, batch_size)

    def estimator(self) -> Any:
        raise NoGradients(f"Model {self.card.name} không hỗ trợ gradient")


class _NoGradientProvider:
    def __init__(self, store: LocalStore) -> None:
        self.real = ModelProvider(store)
        self.calls = 0

    def get(self, card: ModelCard, params: InferenceParams, device: str) -> Any:
        self.calls += 1
        return _NoGradientAdapter(self.real.get(card, params, device))


@dataclass(frozen=True)
class _Pipeline:
    store: LocalStore
    model: dict[str, Any]
    slice: dict[str, Any]
    mapping: dict[str, Any]

    def config(self, attacks: dict[str, list[float]]) -> LocalRunConfig:
        entries = []
        for name, levels in attacks.items():
            spec = get_spec(load_catalog(), name=name)
            entries.append(
                {
                    "attack_spec_id": str(spec.id),
                    "spec_sha256": spec.spec_sha256,
                    "mode": "grid",
                    "grid": {"levels": levels},
                    "seed": 0,
                }
            )
        return LocalRunConfig.model_validate(
            {
                "model_id": self.model["id"],
                "slice_id": self.slice["id"],
                "mapping_id": self.mapping["id"],
                "attacks": entries,
                "device": "cpu",
                "batch_size": 2,
                "failure_cases_per_run": 1,
            }
        )


@pytest.fixture(scope="module")
def pipeline(tmp_path_factory: pytest.TempPathFactory) -> _Pipeline:
    assert WEIGHTS.is_file() and KITTI_ROOT.is_dir(), "Thiếu fixture: chạy `make fixtures`"
    store_dir = tmp_path_factory.mktemp("r1_registry") / "store"

    def cli(*args: str) -> Any:
        result = CliRunner().invoke(app, ["--store-dir", str(store_dir), *args])
        assert result.exit_code == 0, result.output
        return json.loads(result.stdout)

    sha = cli("dataset", "import-kitti", "--root", str(KITTI_ROOT))["dataset_version_sha256"]
    model = cli("model", "register", "--weights", str(WEIGHTS), "--name", "yolov8n-coco")
    slice_spec = cli("slice", "create", "--dataset", sha, "--size", "2", "--seed", "42")
    mapping = cli("mapping", "create", "--dataset", sha, "--model", model["id"])
    return _Pipeline(LocalStore(store_dir), model, slice_spec, mapping)


def test_fake_builder_runs_through_cli_runner(pipeline: _Pipeline) -> None:
    builder = _IdentityBuilder()
    registry = PerturbationRegistry(resolver=lambda _spec: "test.identity")
    registry.register(builder)

    def factory(spec: AttackSpec, estimator: Any) -> Any:
        return registry.build(spec, BuildContext(estimator=estimator))

    report = run_config(
        pipeline.store,
        pipeline.config({"fog": [3]}),
        force=True,
        perturbation_factory=factory,
    )
    assert len(report.outcomes) == 1
    result = report.outcomes[0].result
    assert result.status == "completed", result.status_reason
    assert len(builder.built) == 1
    identity = builder.built[0]
    assert identity.calls >= 1
    assert identity.max_abs_diff == 0.0
    assert result.progress.images_done == result.progress.images_total == 2


def test_white_box_skipped_on_model_without_gradients(pipeline: _Pipeline) -> None:
    provider = _NoGradientProvider(pipeline.store)
    report = run_config(
        pipeline.store,
        pipeline.config({"fgsm": [4], "fog": [3]}),
        force=True,
        model_provider=provider,
    )
    by_name = {outcome.spec_name: outcome.result for outcome in report.outcomes}
    assert set(by_name) == {"fgsm", "fog"}

    fgsm = by_name["fgsm"]
    assert fgsm.status == "skipped"
    assert fgsm.status_reason is not None
    assert fgsm.status_reason.code == "incompatible"
    # Thông điệp của CLI như Phase 2 (`ml_core/runner/run.py` trước R1).
    assert fgsm.status_reason.message == (
        f"fgsm cần gradient nhưng model {pipeline.model['name']} không hỗ trợ gradient"
    )

    fog = by_name["fog"]
    assert fog.status == "completed", fog.status_reason
    assert provider.calls >= 1
