"""validation.md Phase R2, Group 2 — Tự kiểm tra spec (`test_selfcheck.py`). Không cần DB.

- Mọi spec seed pass cả 7 mục.
- Với mỗi mục có một builder giả vi phạm đúng mục đó: chỉ mục đó fail.

Interface (requirements.md Phase R2, Chốt ở Group 0, "Interface cho test nghiệm thu"):
`attacks.selfcheck.SelfcheckInputs`, `attacks.selfcheck.run_selfcheck`. Level của mục 2, 3, 5,
6, 7 là level giữa dải; mục 4 dùng `min`; mục 1 chạy `min`, giữa và `max`.

Builder giả biến đổi ảnh bằng một hàm theo từng điểm ảnh (không phụ thuộc vị trí trong batch), nên
chúng chỉ vi phạm đúng mục được nhắm tới. Mục 7 so hai perturbation dựng độc lập (hai lần
`registry.build`); mục 5 so batch 1 với batch 4 trên cùng một perturbation.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar
from uuid import UUID

import numpy as np
import pytest

from advertest_contracts.enums import AttackKind, PerturbationImageKind, SpecCheckName
from advertest_contracts.ids import content_id
from advertest_contracts.models import AttackSpec, AttackSpecBody, SpecCheckItem
from advertest_contracts.models import compute_spec_sha256 as sha
from attacks.builders import BuildContext, PerturbationRegistry
from attacks.registry import load_catalog
from ml_core.data.loader import SliceLoader
from ml_core.models.estimator import build_estimator
from ml_core.models.wrapper import DEFAULT_INFERENCE_PARAMS, load_detection_model
from ml_core.runner.images import letterbox_mask
from ml_core.store import LocalStore

from .conftest import P5, YOLO_WEIGHTS

ALL = {name.value for name in SpecCheckName}


def SelfcheckInputs(**kwargs: Any) -> Any:  # bọc lớp của Group 2 (import khi chạy)
    from attacks.selfcheck import SelfcheckInputs as inputs_cls

    return inputs_cls(**kwargs)


def run_selfcheck(spec: AttackSpec, inputs: Any, **kwargs: Any) -> Any:
    from attacks.selfcheck import run_selfcheck as run  # Group 2

    return run(spec, inputs, **kwargs)


@pytest.fixture(scope="module")
def kitti(tmp_path_factory: pytest.TempPathFactory) -> tuple[np.ndarray, np.ndarray, list[Any]]:
    """4 ảnh KITTI letterbox, mask vùng ảnh thật và target theo quy ước ART."""
    store_dir: Path = tmp_path_factory.mktemp("r2-selfcheck") / "store"
    root = str(P5.KITTI_ROOT)
    sha_ = P5.ml(store_dir, "dataset", "import-kitti", "--root", root)["dataset_version_sha256"]
    model = P5.ml(store_dir, "model", "register", "--weights", str(YOLO_WEIGHTS), "--name", "y")
    slice_ = P5.ml(store_dir, "slice", "create", "--dataset", sha_, "--size", "4", "--seed", "42")
    mapping = P5.ml(store_dir, "mapping", "create", "--dataset", sha_, "--model", model["id"])
    loader = SliceLoader.from_ids(LocalStore(store_dir), UUID(slice_["id"]), UUID(mapping["id"]))
    batch = next(loader.batches(4))
    targets = [
        {**target, "image_id": image_id, "ignore_boxes": ignore["boxes"]}
        for target, image_id, ignore in zip(
            batch.targets, batch.image_ids, batch.ignore, strict=True
        )
    ]
    return batch.images, letterbox_mask(batch.infos), targets


@pytest.fixture(scope="module")
def inputs(kitti: tuple[np.ndarray, np.ndarray, list[Any]]) -> Any:
    images, masks, targets = kitti
    estimator = build_estimator(load_detection_model(YOLO_WEIGHTS), DEFAULT_INFERENCE_PARAMS, "cpu")
    return SelfcheckInputs(images=images, masks=masks, targets=targets, estimator=estimator)


def _by_name(items: list[SpecCheckItem]) -> dict[str, SpecCheckItem]:
    names = [item.name.value for item in items]
    assert names == [n.value for n in SpecCheckName], names
    return {item.name.value: item for item in items}


# ---------------------------------------------------------------- spec seed


@pytest.mark.parametrize("name", sorted(s.name for s in load_catalog()))
def test_seed_spec_passes_all_items(name: str, inputs: Any) -> None:
    spec = next(s for s in load_catalog() if s.name == name)
    outcome = run_selfcheck(spec, inputs)
    assert outcome.error is None, outcome.error
    items = _by_name(outcome.items)
    assert all(item.passed for item in items.values()), {
        k: v.details for k, v in items.items() if not v.passed
    }
    if spec.kind != AttackKind.ATTACK:  # chuẩn nhiễu chỉ áp với kind = attack
        assert items["norm_bound"].details
    if spec.primary_param.min > 0:  # không có level "không biến đổi"
        assert items["identity"].details


# ---------------------------------------------------------------- builder giả vi phạm từng mục

# (ảnh, mask, level, cỡ batch, salt): salt ngẫu nhiên theo từng lần dựng perturbation.
Transform = Callable[[np.ndarray, np.ndarray, float, int, float], np.ndarray]


def _spec(adapter: str, *, kind: AttackKind = AttackKind.CORRUPTION) -> AttackSpec:
    if kind == AttackKind.ATTACK:
        body: dict[str, Any] = {
            "name": f"fake_{adapter.split('.')[-1]}",
            "version": 1,
            "kind": "attack",
            "access": "white_box",
            "art_class": "FakeAttack",
            "primary_param": {"name": "eps", "type": "continuous", "min": 0, "max": 8,
                              "unit": "1/255"},
            "fixed_params": {"norm": "inf"},
            "cost_model": {"cpu_only": True},
            "requires_gradients": False,
            "adapter": adapter,
        }  # fmt: skip
    else:
        body = {
            "name": f"fake_{adapter.split('.')[-1]}",
            "version": 1,
            "kind": "corruption",
            "access": "not_applicable",
            "art_class": None,
            "primary_param": {"name": "strength", "type": "continuous", "min": 0, "max": 1,
                              "unit": "ratio"},
            "fixed_params": {},
            "cost_model": {"cpu_only": True},
            "requires_gradients": False,
            "adapter": adapter,
        }  # fmt: skip
    digest = sha(AttackSpecBody.model_validate(body))
    return AttackSpec.model_validate({**body, "id": str(content_id(digest)), "spec_sha256": digest})


class _Fake:
    def __init__(self, spec: AttackSpec, transform: Transform) -> None:
        self.spec = spec
        self.transform = transform
        self.salt = float(np.random.default_rng().uniform(0.01, 0.05))

    def apply(
        self,
        images: np.ndarray,
        targets: list[dict[str, Any]],
        level: float,
        seed: int,
        mask: np.ndarray | None = None,
    ) -> np.ndarray:
        if mask is None:
            mask = np.ones((images.shape[0], 1, *images.shape[2:]), dtype=np.float32)
        out = self.transform(images.astype(np.float32), mask, level, len(images), self.salt)
        return out.astype(np.float32)


class _BuilderBase:
    requires: ClassVar[frozenset[str]] = frozenset()
    image_kind: ClassVar[PerturbationImageKind] = PerturbationImageKind.DIFFERENCE
    params_schema: ClassVar[dict[str, Any]] = {"type": "object"}
    transform: ClassVar[Transform]

    def build(self, spec: AttackSpec, ctx: BuildContext) -> Any:
        return _Fake(spec, type(self).transform)

    def linf_eps(self, spec: AttackSpec, level: float) -> float | None:
        return None


def _builder(adapter: str, transform: Transform, kind: AttackKind) -> Any:
    attrs = {"adapter": adapter, "kind": kind, "transform": staticmethod(transform)}
    return type("FakeBuilder", (_BuilderBase,), attrs)()


def _inside(images: np.ndarray, mask: np.ndarray, changed: np.ndarray) -> np.ndarray:
    """Chỉ thay vùng ảnh thật (mask = 1), giữ nguyên vùng pad."""
    return np.where(mask > 0, changed, images)


def _ok(x: np.ndarray, m: np.ndarray, level: float, n: int, salt: float) -> np.ndarray:
    return _inside(x, m, x * (1 - 0.2 * level))


def _crash_at_max(x: np.ndarray, m: np.ndarray, level: float, n: int, salt: float) -> np.ndarray:
    if level >= 1:
        raise RuntimeError("builder giả lỗi ở max")
    return _ok(x, m, level, n, salt)


def _out_of_range(x: np.ndarray, m: np.ndarray, level: float, n: int, salt: float) -> np.ndarray:
    return _inside(x, m, x + 0.8 * level)


def _touch_pad(x: np.ndarray, m: np.ndarray, level: float, n: int, salt: float) -> np.ndarray:
    return x * (1 - 0.2 * level)


def _not_identity(x: np.ndarray, m: np.ndarray, level: float, n: int, salt: float) -> np.ndarray:
    return _inside(x, m, np.clip(x * (1 - 0.2 * level) + 0.01, 0, 1))


def _batch_dependent(x: np.ndarray, m: np.ndarray, level: float, n: int, salt: float) -> np.ndarray:
    return _inside(x, m, x * (1 - 0.05 * n * level))


def _random(x: np.ndarray, m: np.ndarray, level: float, n: int, salt: float) -> np.ndarray:
    """Không tất định giữa hai lần dựng, nhưng một perturbation cho cùng kết quả với mọi batch."""
    return _inside(x, m, np.clip(x * (1 - 0.2 * level) + salt * level, 0, 1))


def _over_eps(x: np.ndarray, m: np.ndarray, level: float, n: int, salt: float) -> np.ndarray:
    eps = level / 255
    return _inside(x, m, np.clip(x + 3 * eps * np.sign(np.sin(1000 * x)), 0, 1))


def _within_eps(x: np.ndarray, m: np.ndarray, level: float, n: int, salt: float) -> np.ndarray:
    eps = level / 255
    return _inside(x, m, np.clip(x + 0.5 * eps * np.sign(np.sin(1000 * x)), 0, 1))


CASES: list[tuple[str, Transform, AttackKind, str | None]] = [
    ("ok", _ok, AttackKind.CORRUPTION, None),
    ("ok_attack", _within_eps, AttackKind.ATTACK, None),
    ("crash", _crash_at_max, AttackKind.CORRUPTION, "runs"),
    ("range", _out_of_range, AttackKind.CORRUPTION, "value_range"),
    ("pad", _touch_pad, AttackKind.CORRUPTION, "pad_unchanged"),
    ("identity", _not_identity, AttackKind.CORRUPTION, "identity"),
    ("batch", _batch_dependent, AttackKind.CORRUPTION, "batch_invariant"),
    ("norm", _over_eps, AttackKind.ATTACK, "norm_bound"),
    ("random", _random, AttackKind.CORRUPTION, "deterministic"),
]


@pytest.mark.parametrize(
    ("name", "transform", "kind", "violated"), CASES, ids=[c[0] for c in CASES]
)
def test_fake_builder_fails_only_its_item(
    name: str,
    transform: Transform,
    kind: AttackKind,
    violated: str | None,
    kitti: tuple[np.ndarray, np.ndarray, list[Any]],
) -> None:
    images, masks, targets = kitti
    adapter = f"test.{name}"
    registry = PerturbationRegistry()
    registry.register(_builder(adapter, transform, kind))
    spec = _spec(adapter, kind=kind)  # attack giả: level là eps theo đơn vị 1/255, max 8
    inputs = SelfcheckInputs(images=images, masks=masks, targets=targets, estimator=None)
    outcome = run_selfcheck(spec, inputs, registry=registry)
    items = _by_name(outcome.items)
    failed = {k for k, v in items.items() if not v.passed}
    assert failed == ({violated} if violated else set()), {k: items[k].details for k in failed}
    for key in failed:
        assert items[key].details
    assert outcome.error is None


def test_timeout_reports_error(kitti: tuple[np.ndarray, np.ndarray, list[Any]]) -> None:
    """Quá giới hạn thời gian: có `error`, kết quả không pass (spec chuyển `check_failed`)."""

    def slow(x: np.ndarray, m: np.ndarray, level: float, n: int, salt: float) -> np.ndarray:
        time.sleep(0.2)
        return _ok(x, m, level, n, salt)

    images, masks, targets = kitti
    registry = PerturbationRegistry()
    registry.register(_builder("test.slow", slow, AttackKind.CORRUPTION))
    inputs = SelfcheckInputs(images=images, masks=masks, targets=targets, estimator=None)
    outcome = run_selfcheck(_spec("test.slow"), inputs, registry=registry, timeout_s=0.5)
    assert outcome.error
    assert len(outcome.items) < len(ALL) or not all(i.passed for i in outcome.items)
