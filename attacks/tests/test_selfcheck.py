"""Nhánh của `attacks/selfcheck.py` không cần model YOLO.

Test nghiệm thu `phase_r2/test_selfcheck.py` chạy spec seed và builder giả vi phạm từng mục trên
ảnh KITTI.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar
from uuid import uuid4

import numpy as np
import pytest
import torch

from advertest_contracts.enums import AttackKind, PerturbationImageKind, SpecCheckName
from advertest_contracts.models import AttackSpec, AttackSpecBody
from advertest_contracts.perturbation import Perturbation
from attacks.builders import GRADIENTS, BuildContext, PerturbationRegistry
from attacks.selfcheck import SelfcheckInputs, _load_spec, mid_level, run_selfcheck
from attacks.tests import fake_detector as fd
from attacks.tests.transform_helpers import letterbox_batch, spec, targets


def _inputs(estimator: Any = None) -> SelfcheckInputs:
    images, masks = letterbox_batch(4)
    return SelfcheckInputs(images=images, masks=masks, targets=targets(4), estimator=estimator)


def _items(outcome: Any) -> dict[str, Any]:
    return {item.name.value: item for item in outcome.items}


class _Scale:
    """Perturbation giả: nhân vùng ảnh thật; `bump` cộng thêm khi chạy batch 1."""

    def __init__(self, spec: AttackSpec, bump: float) -> None:
        self.spec = spec
        self.bump = bump

    def apply(
        self,
        images: np.ndarray,
        targets: list[dict[str, Any]],
        level: float,
        seed: int,
        mask: np.ndarray | None = None,
    ) -> np.ndarray:
        assert mask is not None
        changed = images * (1 - level / 255) + (self.bump if len(images) == 1 else 0.0)
        return np.where(mask > 0, np.clip(changed, 0, 1), images).astype(np.float32)


class _GradientBuilder:
    """Builder cần gradient như FGSM/PGD; `bump` mô phỏng kết quả batch 1 lệch batch 4."""

    adapter: ClassVar[str] = "test.gradient"
    kind: ClassVar[AttackKind] = AttackKind.ATTACK
    requires: ClassVar[frozenset[str]] = frozenset({GRADIENTS})
    image_kind: ClassVar[PerturbationImageKind] = PerturbationImageKind.AMPLIFIED_NOISE
    params_schema: ClassVar[dict[str, Any]] = {"type": "object"}
    bump: ClassVar[float] = 0.0

    def build(self, spec: AttackSpec, ctx: BuildContext) -> Perturbation:
        assert ctx.estimator is not None
        return _Scale(spec, self.bump)

    def linf_eps(self, spec: AttackSpec, level: float) -> float | None:
        return None


class _Broken(_GradientBuilder):
    def build(self, spec: AttackSpec, ctx: BuildContext) -> Perturbation:
        raise RuntimeError("builder hỏng")


def _registry(builder: Any) -> PerturbationRegistry:
    registry = PerturbationRegistry(resolver=lambda _spec: builder.adapter)
    registry.register(builder)
    return registry


@pytest.mark.parametrize(("name", "level"), [("fgsm", 16.0), ("fog", 3.0), ("adv_patch", 0.135)])
def test_mid_level(name: str, level: float) -> None:
    assert mid_level(spec(name)) == pytest.approx(level)


def test_invalid_spec_is_error_without_items() -> None:
    bad = spec("fog").model_copy(update={"adapter": "corruption.khong_co"})
    outcome = run_selfcheck(bad, _inputs())
    assert outcome.items == []
    assert outcome.error is not None and "corruption.khong_co" in outcome.error
    assert not outcome.passed


def test_seed_corruption_passes_and_converts_to_result() -> None:
    fog = spec("fog")
    outcome = run_selfcheck(fog, _inputs())
    assert outcome.error is None
    assert [item.name for item in outcome.items] == list(SpecCheckName)
    assert outcome.passed
    items = _items(outcome)
    assert items["identity"].details  # min = 1 > 0: bỏ qua
    assert items["norm_bound"].details  # kind = corruption: bỏ qua

    now = datetime.now(UTC)
    target = uuid4()
    result = outcome.to_result(fog.id, checked_at=now, worker_target_id=target)
    assert (result.spec_id, result.passed, result.error) == (fog.id, True, None)
    assert result.items == outcome.items
    assert (result.checked_at, result.worker_target_id) == (now, target)


def test_build_error_fails_items_without_error() -> None:
    outcome = run_selfcheck(spec("fgsm"), _inputs(fd.estimator()), registry=_registry(_Broken()))
    assert outcome.error is None
    items = _items(outcome)
    assert not items["runs"].passed
    assert "builder hỏng" in items["runs"].details
    for name in ("value_range", "pad_unchanged", "identity", "batch_invariant", "deterministic"):
        assert not items[name].passed, name
        assert "builder hỏng" in items[name].details, name


def test_gradient_attack_batch_difference_is_recorded_not_failed() -> None:
    """Attack dùng gradient: batch 1 lệch batch 4 nhưng vẫn hợp lệ thì mục 5 pass, ghi độ lệch."""

    class Drift(_GradientBuilder):
        bump = 0.01  # < eps ở level giữa (16/255)

    outcome = run_selfcheck(spec("fgsm"), _inputs(fd.estimator()), registry=_registry(Drift()))
    items = _items(outcome)
    assert outcome.passed, {k: v.details for k, v in items.items() if not v.passed}
    assert "0.01" in items["batch_invariant"].details


def test_gradient_attack_batch_one_over_eps_fails() -> None:
    class OverEps(_GradientBuilder):
        bump = 0.2  # > eps ở level giữa

    outcome = run_selfcheck(spec("fgsm"), _inputs(fd.estimator()), registry=_registry(OverEps()))
    items = _items(outcome)
    failed = {name for name, item in items.items() if not item.passed}
    assert failed == {"batch_invariant"}
    assert "chuẩn nhiễu" in items["batch_invariant"].details


def test_torch_threads_restored() -> None:
    threads = torch.get_num_threads()
    run_selfcheck(spec("contrast"), _inputs())
    assert torch.get_num_threads() == threads


def test_load_spec_accepts_body_and_full_spec(tmp_path: Path) -> None:
    fog = spec("fog")
    full = tmp_path / "full.json"
    full.write_text(fog.model_dump_json())
    assert _load_spec(full) == fog

    body = tmp_path / "body.json"
    fields = set(AttackSpecBody.model_fields)
    body.write_text(json.dumps(fog.model_dump(mode="json", include=fields)))
    assert _load_spec(body).spec_sha256 == fog.spec_sha256
