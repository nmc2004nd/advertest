"""Train patch bằng `RobustDPatch` của ART (requirements.md Phase 6, mục Patch attack; task 12).

`RobustDPatch.generate` tự chạy hết `max_iter` vòng, không có chỗ móc checkpoint hay tiến độ, nên
module này gọi nó mỗi lần một vòng (`max_iter = 1`) và giữ patch giữa các lần gọi (gán
`attack._patch`: ART không có API đặt patch khởi tạo).

- Untargeted: ART lấy prediction trên ảnh sạch (sau biến đổi ngẫu nhiên) làm nhãn và tăng loss.
- Số ngẫu nhiên: patch khởi tạo lấy từ `np.random.default_rng(seed)`; phép biến đổi của ART dùng
  module `random` chung, trạng thái của nó được lưu trong `TrainingState` để train tiếp từ
  checkpoint cho cùng kết quả như train liền. Trạng thái `random` chung của tiến trình được khôi
  phục sau khi train xong.
- Giá trị mục tiêu (người dùng chốt ở Group 2): trung bình `compute_loss` của detector trên ảnh
  huấn luyện đã dán patch (không biến đổi ngẫu nhiên), so với prediction trên ảnh sạch tính một
  lần. Attack untargeted làm giá trị này tăng.
- ART làm tròn ảnh về bội số của `learning_rate` ở bước chỉnh độ sáng (hành vi gốc của ART).
"""

from __future__ import annotations

import io
import json
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np
from art.attacks.evasion import RobustDPatch
from art.estimators.estimator import BaseEstimator
from numpy.typing import NDArray

from advertest_contracts.enums import AttackKind
from advertest_contracts.models import AttackSpec, TrainingParams
from advertest_contracts.perturbation import ImageBatch, MaskBatch
from attacks.art_adapter import UnsupportedAttack
from attacks.patch.geometry import centered, common_region, image_regions, patch_side

PatchArray = NDArray[np.float32]  # (3, side, side) trong [0, 1]
_CHECKPOINT_VERSION = 1


@dataclass(frozen=True)
class PatchGeometry:
    side: int
    top: int
    left: int


@dataclass(frozen=True)
class TrainingState:
    """Trạng thái train sau `iterations_done` vòng; là nội dung của checkpoint."""

    patch: PatchArray
    iterations_done: int
    objective_history: list[float] = field(default_factory=list)
    random_state: str = ""  # JSON của random.getstate()
    seconds: float = 0.0

    def to_bytes(self) -> bytes:
        """Checkpoint `.npz` (không dùng pickle); tự ghi số vòng lặp đã xong."""
        buffer = io.BytesIO()
        np.savez_compressed(
            buffer,
            version=np.int64(_CHECKPOINT_VERSION),
            patch=self.patch,
            iterations_done=np.int64(self.iterations_done),
            objective_history=np.asarray(self.objective_history, dtype=np.float64),
            random_state=np.asarray(self.random_state),
            seconds=np.float64(self.seconds),
        )
        return buffer.getvalue()

    @classmethod
    def from_bytes(cls, data: bytes) -> TrainingState:
        with np.load(io.BytesIO(data), allow_pickle=False) as npz:
            if int(npz["version"]) != _CHECKPOINT_VERSION:
                raise ValueError(f"Checkpoint patch version {int(npz['version'])} không hỗ trợ")
            return cls(
                patch=np.asarray(npz["patch"], dtype=np.float32),
                iterations_done=int(npz["iterations_done"]),
                objective_history=[float(v) for v in npz["objective_history"]],
                random_state=str(npz["random_state"]),
                seconds=float(npz["seconds"]),
            )


def _dump_random_state(state: Any) -> str:
    return json.dumps(state)


def _load_random_state(text: str) -> Any:
    version, internal, gauss = json.loads(text)
    return (version, tuple(internal), gauss)


def training_params(spec: AttackSpec) -> TrainingParams:
    if (
        spec.kind != AttackKind.ATTACK
        or spec.art_class != "RobustDPatch"
        or not spec.requires_training
        or spec.training is None
        or spec.primary_param.name != "area_ratio"
    ):
        raise UnsupportedAttack(f"{spec.name}: cần spec RobustDPatch có training và area_ratio")
    return spec.training


def brightness_range(spec: AttackSpec) -> tuple[float, float]:
    value = spec.fixed_params.get("brightness_range", [1.0, 1.0])
    if not isinstance(value, list) or len(value) != 2:
        raise UnsupportedAttack(f"{spec.name}: brightness_range phải là [thấp, cao]")
    low, high = value
    if not isinstance(low, int | float) or not isinstance(high, int | float) or low > high:
        raise UnsupportedAttack(f"{spec.name}: brightness_range phải là [thấp, cao]")
    return (float(low), float(high))


def paste(images: ImageBatch, patch: PatchArray, tops: list[int], lefts: list[int]) -> ImageBatch:
    """Bản sao của `images` đã dán `patch` tại (top, left) của từng ảnh."""
    side = patch.shape[1]
    out = images.copy()
    for i, (top, left) in enumerate(zip(tops, lefts, strict=True)):
        out[i, :, top : top + side, left : left + side] = patch
    return out


ProgressCallback = Callable[[TrainingState], bool]
CheckpointCallback = Callable[[TrainingState], None]


class PatchTrainer:
    """Train patch cho một (spec, estimator, area_ratio, seed) trên ảnh của slice huấn luyện."""

    def __init__(
        self,
        spec: AttackSpec,
        estimator: BaseEstimator,
        *,
        area_ratio: float,
        seed: int,
        batch_size: int,
    ) -> None:
        self.params = training_params(spec)
        param = spec.primary_param
        if not param.min <= area_ratio <= param.max:
            raise ValueError(
                f"{spec.name}: area_ratio {area_ratio} ngoài dải [{param.min}, {param.max}]"
            )
        if batch_size < 1:
            raise ValueError("batch_size phải dương")
        self.spec = spec
        self.estimator = estimator
        self.area_ratio = area_ratio
        self.seed = seed
        self.batch_size = batch_size
        self.brightness_range = brightness_range(spec)

    # ------------------------------------------------------------ hình học, trạng thái đầu

    def geometry(self, images: ImageBatch, mask: MaskBatch | None) -> PatchGeometry:
        n, _, height, width = images.shape
        region = common_region(image_regions(mask, n, height, width))
        side = patch_side(self.area_ratio, region)
        top, left = centered(side, region)
        return PatchGeometry(side=side, top=top, left=left)

    def initial_state(self, side: int) -> TrainingState:
        rng = np.random.default_rng(self.seed)
        patch = (rng.integers(0, 255, size=(3, side, side)) / 255.0).astype(np.float32)
        return TrainingState(
            patch=patch,
            iterations_done=0,
            random_state=_dump_random_state(random.Random(self.seed).getstate()),
        )

    # ------------------------------------------------------------ train

    def train(
        self,
        images: ImageBatch,
        mask: MaskBatch | None,
        *,
        state: TrainingState | None = None,
        on_progress: ProgressCallback | None = None,
        on_checkpoint: CheckpointCallback | None = None,
        max_iter: int | None = None,
    ) -> TrainingState:
        """Train tới `max_iter` vòng (mặc định `training.max_iter`), tiếp từ `state` nếu có.

        `on_checkpoint` được gọi ở vòng 0 (khi bắt đầu mới) và sau mỗi `checkpoint_every` vòng;
        `on_progress` được gọi sau mỗi vòng, trả `False` thì dừng (giới hạn, hủy) và trả trạng thái
        hiện tại.
        """
        if images.ndim != 4 or images.dtype != np.float32 or images.shape[1] != 3:
            raise ValueError(
                f"images phải là float32 (N, 3, H, W), nhận {images.dtype} {images.shape}"
            )
        total = self.params.max_iter if max_iter is None else max_iter
        geometry = self.geometry(images, mask)
        if state is None:
            state = self.initial_state(geometry.side)
            if on_checkpoint is not None:
                on_checkpoint(state)
        if state.patch.shape != (3, geometry.side, geometry.side):
            raise ValueError(
                f"Patch trong checkpoint có shape {state.patch.shape}, cần"
                f" {(3, geometry.side, geometry.side)}"
            )
        attack = RobustDPatch(
            estimator=self.estimator,
            patch_shape=(3, geometry.side, geometry.side),
            patch_location=(geometry.top, geometry.left),  # (hàng, cột)
            crop_range=(0, 0),
            brightness_range=self.brightness_range,
            rotation_weights=(1, 0, 0, 0),
            sample_size=self.params.sample_size,
            learning_rate=self.params.learning_rate,
            max_iter=1,
            batch_size=self.batch_size,
            targeted=False,
            verbose=False,
        )
        clean = self._predict(images)
        outer_random = random.getstate()
        try:
            while state.iterations_done < total:
                started = time.perf_counter()
                random.setstate(_load_random_state(state.random_state))
                attack._patch = state.patch.copy()
                attack.generate(images)
                patch = np.asarray(attack._patch, dtype=np.float32)
                next_random = _dump_random_state(random.getstate())
                objective = self.objective(images, patch, geometry, clean)
                state = replace(
                    state,
                    patch=patch,
                    iterations_done=state.iterations_done + 1,
                    objective_history=[*state.objective_history, objective],
                    random_state=next_random,
                    seconds=state.seconds + (time.perf_counter() - started),
                )
                if on_checkpoint is not None and (
                    state.iterations_done % self.params.checkpoint_every == 0
                ):
                    on_checkpoint(state)
                if on_progress is not None and not on_progress(state):
                    break
        finally:
            random.setstate(outer_random)
        return state

    def objective(
        self,
        images: ImageBatch,
        patch: PatchArray,
        geometry: PatchGeometry,
        clean: list[dict[str, Any]],
    ) -> float:
        """Trung bình loss của detector trên ảnh đã dán patch so với prediction ảnh sạch."""
        n = len(images)
        patched = paste(images, patch, [geometry.top] * n, [geometry.left] * n)
        total = 0.0
        for start in range(0, n, self.batch_size):
            end = min(start + self.batch_size, n)
            loss = self.estimator.compute_loss(x=patched[start:end], y=clean[start:end])
            total += float(np.asarray(_to_numpy(loss)).sum())
        return total / n

    def _predict(self, images: ImageBatch) -> list[dict[str, Any]]:
        predictions: list[dict[str, Any]] = self.estimator.predict(
            images, batch_size=self.batch_size
        )
        return predictions


def _to_numpy(value: Any) -> Any:
    detach = getattr(value, "detach", None)
    return detach().cpu().numpy() if callable(detach) else value
