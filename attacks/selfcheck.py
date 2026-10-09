"""Tự kiểm tra attack spec (requirements.md Phase R2, `### Tự kiểm tra spec`; plan.md bước 11).

`run_selfcheck` chạy 7 mục theo thứ tự `SpecCheckName` trên 4 ảnh letterbox (`SelfcheckInputs`):

1. `runs`: dựng và `apply` không lỗi tại `min`, level giữa và `max`.
2. `value_range`: ảnh ra `float32` trong [0, 1], đúng shape (level giữa).
3. `pad_unchanged`: điểm ảnh có mask = 0 giữ nguyên tuyệt đối (level giữa).
4. `identity`: `min = 0` cho ảnh y hệt đầu vào; `min > 0` thì bỏ qua (`passed` kèm lý do).
5. `batch_invariant`: cùng một perturbation, từng ảnh chạy batch 1 khớp kết quả batch 4 (sai số
   1e-6 với `kind = attack`, tuyệt đối với kind khác).
6. `norm_bound`: với `kind = attack`, chuẩn nhiễu theo `fixed_params.norm` ≤ eps + 1e-6; kind khác
   hoặc spec không có `norm` (patch) thì bỏ qua.
7. `deterministic`: perturbation thứ hai dựng độc lập, cùng seed, cho ảnh y hệt.

Level giữa là `min + 0.5·(max - min)`, tham số rời rạc lấy `values[(n - 1) // 2]`. Kết quả của mục 1
được dùng lại cho mục 2, 3, 4, 6 và làm vế batch 4 của mục 5. Spec cần train dùng patch ngẫu nhiên
có seed cố định (`PatchTrainer.initial_state`), dựng riêng cho từng level vì patch gắn với
`area_ratio`.

Lỗi trong một lần dựng hay `apply` làm fail mục cần kết quả đó, không dừng cả lượt. `error` dành cho
lỗi ngoài các mục: spec không hợp registry (`InvalidSpec`) và quá giới hạn thời gian. Giới hạn thời
gian được kiểm trước và sau mỗi lần dựng hay `apply` (không cắt ngang một lần `apply`); cắt cứng là
việc của tiến trình gọi.

Kiểm tra chạy với torch 1 luồng; số luồng cũ được đặt lại khi xong. Lõi không import `ml_core`;
CLI (`python -m attacks.selfcheck <spec.json>`) dựng đầu vào từ fixture qua `ml_core` trong `main`.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import numpy as np
import torch
from art.estimators.estimator import BaseEstimator

from advertest_contracts.enums import AttackKind, SpecCheckName
from advertest_contracts.ids import content_id
from advertest_contracts.models import (
    AttackSpec,
    AttackSpecBody,
    SpecCheckItem,
    SpecCheckResult,
    compute_spec_sha256,
)
from advertest_contracts.perturbation import ImageBatch, MaskBatch, Perturbation
from attacks.art_adapter import level_to_eps
from attacks.builders import DEFAULT_REGISTRY, BuildContext, InvalidSpec, PerturbationRegistry
from attacks.patch.training import PatchTrainer

__all__ = ["SelfcheckInputs", "SelfcheckOutcome", "main", "mid_level", "run_selfcheck"]

DEFAULT_TIMEOUT_S = 120.0
ATTACK_TOLERANCE = 1e-6  # mục 5 với kind = attack; mục 6 cộng thêm vào eps


@dataclass(frozen=True)
class SelfcheckInputs:
    images: ImageBatch  # (4, C, H, W) letterbox, float32 [0, 1]
    masks: MaskBatch  # (4, 1, H, W): 1 vùng ảnh thật, 0 vùng pad
    targets: list[dict[str, Any]]  # ground truth theo quy ước ART (`boxes`, `labels`, ...)
    estimator: BaseEstimator | None  # None khi spec không cần gradient


@dataclass(frozen=True)
class SelfcheckOutcome:
    items: list[SpecCheckItem]
    error: str | None = None

    @property
    def passed(self) -> bool:
        return (
            self.error is None
            and [item.name for item in self.items] == list(SpecCheckName)
            and all(item.passed for item in self.items)
        )

    def to_result(
        self, spec_id: UUID, *, checked_at: datetime, worker_target_id: UUID
    ) -> SpecCheckResult:
        return SpecCheckResult(
            spec_id=spec_id,
            items=self.items,
            passed=self.passed,
            error=self.error,
            checked_at=checked_at,
            worker_target_id=worker_target_id,
        )


class _Timeout(Exception):
    pass


def mid_level(spec: AttackSpec) -> float:
    """Level giữa dải của spec (requirements.md Phase R2, Interface cho test nghiệm thu)."""
    param = spec.primary_param
    if param.type == "discrete" and param.values:
        return float(param.values[(len(param.values) - 1) // 2])
    return param.min + 0.5 * (param.max - param.min)


def _describe(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


class _Session:
    """Dựng và chạy perturbation cho một lượt kiểm tra; nhớ kết quả trên cả batch theo level."""

    def __init__(
        self,
        spec: AttackSpec,
        inputs: SelfcheckInputs,
        registry: PerturbationRegistry,
        seed: int,
        deadline: float,
        timeout_s: float,
    ) -> None:
        self.spec = spec
        self.inputs = inputs
        self.registry = registry
        self.seed = seed
        self.deadline = deadline
        self.timeout_s = timeout_s
        self._perturbations: dict[float, Perturbation] = {}
        self._outputs: dict[float, ImageBatch | Exception] = {}

    def check_time(self) -> None:
        if time.monotonic() > self.deadline:
            raise _Timeout(f"quá giới hạn {self.timeout_s:g} giây")

    def build(self, level: float) -> Perturbation:
        """Perturbation mới; spec cần train nhận patch ngẫu nhiên có seed cố định cho `level`."""
        self.check_time()
        ctx = BuildContext(estimator=self.inputs.estimator)
        if self.spec.requires_training and self.inputs.estimator is not None:
            trainer = PatchTrainer(
                self.spec, self.inputs.estimator, area_ratio=level, seed=self.seed
            )
            geometry = trainer.geometry(self.inputs.images, self.inputs.masks)
            patch = trainer.initial_state(geometry.side).patch
            ctx = BuildContext(estimator=self.inputs.estimator, patch=patch, area_ratio=level)
        perturbation = self.registry.build(self.spec, ctx)
        self.check_time()
        return perturbation

    def perturbation(self, level: float) -> Perturbation:
        """Perturbation dùng chung ở `level`; spec không cần train dùng một cho mọi level."""
        key = level if self.spec.requires_training else 0.0
        if key not in self._perturbations:
            self._perturbations[key] = self.build(level)
        return self._perturbations[key]

    def apply(self, perturbation: Perturbation, level: float, index: int | None = None) -> Any:
        """`apply` trên cả batch, hoặc chỉ ảnh `index` (batch 1)."""
        part = slice(None) if index is None else slice(index, index + 1)
        targets = self.inputs.targets if index is None else self.inputs.targets[part]
        self.check_time()
        out = perturbation.apply(
            self.inputs.images[part].copy(), targets, level, self.seed, self.inputs.masks[part]
        )
        self.check_time()
        return out

    def output(self, level: float) -> ImageBatch:
        """Kết quả trên cả batch ở `level`; lỗi lần đầu được nhớ và báo lại ở các lần sau."""
        if level not in self._outputs:
            try:
                self._outputs[level] = self.apply(self.perturbation(level), level)
            except _Timeout:
                raise
            except Exception as exc:  # lỗi của builder: mục cần kết quả này fail
                self._outputs[level] = exc
        result = self._outputs[level]
        if isinstance(result, Exception):
            raise result
        return result


_Check = Callable[[_Session], tuple[bool, str | None]]


def _output_or_fail(session: _Session, level: float) -> ImageBatch:
    try:
        return session.output(level)
    except _Timeout:
        raise
    except Exception as exc:
        raise _ItemFailed(f"không chạy được ở level {level:g}: {_describe(exc)}") from exc


class _ItemFailed(Exception):
    pass


def _runs(session: _Session) -> tuple[bool, str | None]:
    param = session.spec.primary_param
    failures: list[str] = []
    for level in dict.fromkeys([param.min, mid_level(session.spec), param.max]):
        try:
            session.output(level)
        except _Timeout:
            raise
        except Exception as exc:
            failures.append(f"level {level:g}: {_describe(exc)}")
    return (not failures, "; ".join(failures) or None)


def _value_range(session: _Session) -> tuple[bool, str | None]:
    out = _output_or_fail(session, mid_level(session.spec))
    images = session.inputs.images
    if not isinstance(out, np.ndarray) or out.dtype != np.float32:
        kind = out.dtype if isinstance(out, np.ndarray) else type(out).__name__
        return (False, f"ảnh ra phải là float32, nhận {kind}")
    if out.shape != images.shape:
        return (False, f"shape ảnh ra {out.shape} khác đầu vào {images.shape}")
    if not np.all(np.isfinite(out)):
        return (False, "ảnh ra có NaN hoặc vô cực")
    low, high = float(out.min()), float(out.max())
    if low < 0 or high > 1:
        return (False, f"giá trị ngoài [0, 1]: min {low:g}, max {high:g}")
    return (True, None)


def _pad_unchanged(session: _Session) -> tuple[bool, str | None]:
    out = _output_or_fail(session, mid_level(session.spec))
    images = session.inputs.images
    pad = np.broadcast_to(session.inputs.masks == 0, images.shape)
    if not pad.any():
        return (True, "đầu vào không có vùng pad")
    if out.shape != images.shape:
        return (False, f"shape ảnh ra {out.shape} khác đầu vào {images.shape}")
    changed = int(np.count_nonzero(out[pad] != images[pad]))
    if changed:
        return (False, f"{changed} giá trị trong vùng pad bị thay đổi")
    return (True, None)


def _identity(session: _Session) -> tuple[bool, str | None]:
    low = session.spec.primary_param.min
    if low != 0:
        return (True, f"bỏ qua: min = {low:g} khác 0, không có level không biến đổi")
    out = _output_or_fail(session, low)
    if out.shape != session.inputs.images.shape or not np.array_equal(out, session.inputs.images):
        return (False, "level 0 làm thay đổi ảnh")
    return (True, None)


def _batch_invariant(session: _Session) -> tuple[bool, str | None]:
    level = mid_level(session.spec)
    full = _output_or_fail(session, level)
    perturbation = session.perturbation(level)
    tolerance = ATTACK_TOLERANCE if session.spec.kind == AttackKind.ATTACK else 0.0
    failures: list[str] = []
    for index in range(len(session.inputs.images)):
        try:
            single = session.apply(perturbation, level, index)
        except _Timeout:
            raise
        except Exception as exc:
            failures.append(f"ảnh {index}: batch 1 lỗi {_describe(exc)}")
            continue
        if single.shape != full[index : index + 1].shape:
            failures.append(f"ảnh {index}: shape batch 1 {single.shape}")
            continue
        diff = float(np.max(np.abs(single.astype(np.float64) - full[index : index + 1])))
        if diff > tolerance:
            failures.append(f"ảnh {index}: lệch {diff:.3g} > {tolerance:g}")
    return (not failures, "; ".join(failures) or None)


def _norm_order(value: Any) -> float:
    if str(value) == "inf":
        return float(np.inf)
    return float(value)


def _norm_bound(session: _Session) -> tuple[bool, str | None]:
    spec = session.spec
    if spec.kind != AttackKind.ATTACK:
        return (True, f"bỏ qua: chỉ áp với kind = attack (spec có kind = {spec.kind})")
    if "norm" not in spec.fixed_params:
        return (True, "bỏ qua: spec không khai báo fixed_params.norm")
    level = mid_level(spec)
    try:
        order = _norm_order(spec.fixed_params["norm"])
        eps = level_to_eps(spec, level)
    except (KeyError, TypeError, ValueError) as exc:
        return (False, f"không tính được eps hay norm: {_describe(exc)}")
    out = _output_or_fail(session, level)
    images = session.inputs.images
    if out.shape != images.shape:
        return (False, f"shape ảnh ra {out.shape} khác đầu vào {images.shape}")
    delta = (out.astype(np.float64) - images.astype(np.float64)).reshape(len(images), -1)
    norms = np.linalg.norm(delta, ord=order, axis=1)
    worst = float(norms.max())
    if worst > eps + ATTACK_TOLERANCE:
        return (
            False,
            f"chuẩn nhiễu {worst:.6g} > eps {eps:.6g} (norm {spec.fixed_params['norm']})",
        )
    return (True, None)


def _deterministic(session: _Session) -> tuple[bool, str | None]:
    level = mid_level(session.spec)
    first = _output_or_fail(session, level)
    try:
        second = session.apply(session.build(level), level)
    except _Timeout:
        raise
    except Exception as exc:
        return (False, f"lần chạy thứ hai lỗi: {_describe(exc)}")
    if second.shape != first.shape or not np.array_equal(second, first):
        return (False, "hai lần chạy cùng seed cho ảnh khác nhau")
    return (True, None)


_CHECKS: list[tuple[SpecCheckName, _Check]] = [
    (SpecCheckName.RUNS, _runs),
    (SpecCheckName.VALUE_RANGE, _value_range),
    (SpecCheckName.PAD_UNCHANGED, _pad_unchanged),
    (SpecCheckName.IDENTITY, _identity),
    (SpecCheckName.BATCH_INVARIANT, _batch_invariant),
    (SpecCheckName.NORM_BOUND, _norm_bound),
    (SpecCheckName.DETERMINISTIC, _deterministic),
]


def run_selfcheck(
    spec: AttackSpec,
    inputs: SelfcheckInputs,
    *,
    registry: PerturbationRegistry = DEFAULT_REGISTRY,
    seed: int = 0,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> SelfcheckOutcome:
    """Chạy 7 mục tự kiểm tra; trả các mục đã chạy xong và `error` khi có lỗi ngoài các mục."""
    try:
        registry.validate(spec)
    except InvalidSpec as exc:
        return SelfcheckOutcome(items=[], error=str(exc))

    items: list[SpecCheckItem] = []
    threads = torch.get_num_threads()
    torch.set_num_threads(1)
    session = _Session(spec, inputs, registry, seed, time.monotonic() + timeout_s, timeout_s)
    try:
        for name, check in _CHECKS:
            try:
                passed, details = check(session)
            except _ItemFailed as exc:
                passed, details = False, str(exc)
            items.append(SpecCheckItem(name=name, passed=passed, details=details))
    except _Timeout as exc:
        return SelfcheckOutcome(items=items, error=str(exc))
    finally:
        torch.set_num_threads(threads)
    return SelfcheckOutcome(items=items)


# ---------------------------------------------------------------- CLI


def _load_spec(path: Path) -> AttackSpec:
    """`AttackSpec` (có `id`, `spec_sha256`) hoặc `AttackSpecBody` (server chưa tính hash)."""
    data = json.loads(path.read_text())
    if "spec_sha256" in data:
        return AttackSpec.model_validate(data)
    body = AttackSpecBody.model_validate(data)
    digest = compute_spec_sha256(body)
    return AttackSpec.model_validate(
        {**body.model_dump(mode="json"), "id": str(content_id(digest)), "spec_sha256": digest}
    )


def _fixture_inputs(kitti_root: Path, weights: Path) -> SelfcheckInputs:
    """4 ảnh KITTI letterbox với target đã map sang class của model (slice seed 42) và estimator
    ART của model YOLO trên CPU."""
    from ml_core.data.dataset import save_dataset
    from ml_core.data.kitti import import_kitti
    from ml_core.data.loader import SliceLoader
    from ml_core.data.mapping import build_mapping
    from ml_core.data.slice import create_slice, preset_filter
    from ml_core.models.estimator import build_estimator
    from ml_core.models.register import load_check_images, register_model
    from ml_core.models.wrapper import DEFAULT_INFERENCE_PARAMS, load_detection_model
    from ml_core.runner.images import letterbox_mask
    from ml_core.store import LocalStore

    with tempfile.TemporaryDirectory(prefix="selfcheck-") as tmp:
        store = LocalStore(Path(tmp))
        manifest = import_kitti(kitti_root)
        dataset_sha = save_dataset(store, manifest, kitti_root)
        card = register_model(store, weights, "selfcheck", load_check_images(), device="cpu")
        slice_spec = create_slice(manifest, 4, 42, preset_filter("kitti-coco"))
        mapping = build_mapping(dataset_sha, card, "kitti-coco")
        batch = next(SliceLoader(store, slice_spec, mapping, card).batches(4))
    targets = [
        {**target, "image_id": image_id, "ignore_boxes": ignore["boxes"]}
        for target, image_id, ignore in zip(
            batch.targets, batch.image_ids, batch.ignore, strict=True
        )
    ]
    estimator = build_estimator(load_detection_model(weights), DEFAULT_INFERENCE_PARAMS, "cpu")
    return SelfcheckInputs(
        images=batch.images, masks=letterbox_mask(batch.infos), targets=targets, estimator=estimator
    )


def main(argv: Sequence[str] | None = None) -> int:
    """In kết quả các mục dạng JSON; mã thoát 0 khi pass, 1 khi fail."""
    from ml_core.fixtures import FIXTURES_DIR

    parser = argparse.ArgumentParser(
        prog="python -m attacks.selfcheck", description="Tự kiểm tra attack spec trên ảnh fixture"
    )
    parser.add_argument("spec", type=Path, help="File JSON của AttackSpec hoặc AttackSpecBody")
    parser.add_argument("--kitti-root", type=Path, default=FIXTURES_DIR / "kitti")
    parser.add_argument("--weights", type=Path, default=FIXTURES_DIR / "yolov8n.pt")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S)
    args = parser.parse_args(argv)

    spec = _load_spec(args.spec)
    inputs = _fixture_inputs(args.kitti_root, args.weights)
    outcome = run_selfcheck(spec, inputs, seed=args.seed, timeout_s=args.timeout)
    report = {
        "spec": f"{spec.name} v{spec.version}",
        "passed": outcome.passed,
        "error": outcome.error,
        "items": [item.model_dump(mode="json") for item in outcome.items],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if outcome.passed else 1


if __name__ == "__main__":
    sys.exit(main())
