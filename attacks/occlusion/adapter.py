"""Occlusion theo interface `Perturbation` (requirements.md Phase 6, mục Occlusion).

Với mỗi box ground truth đã map (`targets[i]["boxes"]`, xyxy pixel letterbox): một hình chữ nhật
cùng tỉ lệ với box, diện tích ≈ `level` nhân diện tích box, vị trí ngẫu nhiên theo seed của ảnh, nằm
hoàn toàn trong box, tô màu `fill_255`/255.

- Hình chữ nhật gồm các pixel nguyên nằm trọn trong box; kích thước là cặp số nguyên gần diện tích
  yêu cầu nhất (cùng sai số thì gần tỉ lệ box hơn).
- Pixel chạm vào ignore region (`targets[i]["ignore_boxes"]`, tùy chọn, xyxy letterbox; người dùng
  chốt ở Group 1) và pixel có mask = 0 không bị tô, nên phần tô có thể nhỏ hơn tỉ lệ khi box chồng
  ignore region.
- Box được xử lý theo thứ tự trong `targets`; mỗi box rút vị trí từ bộ sinh số của ảnh.

Đây là phép thử chịu tải mô phỏng vật che khuất, không phải năng lực của kẻ tấn công.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from numpy.typing import NDArray

from advertest_contracts.enums import AttackKind
from advertest_contracts.models import AttackSpec
from advertest_contracts.perturbation import ImageBatch, MaskBatch
from attacks.common.checks import UnsupportedTransform, check_inputs
from attacks.common.seed import image_rng, target_image_id

DEFAULT_FILL_255 = 114


def _boxes(target: dict[str, Any], key: str, *, required: bool) -> NDArray[np.float64]:
    """Box (K, 4) của target. Khóa bắt buộc mà vắng (hoặc None) thì báo lỗi, để occlusion không
    lặng lẽ bỏ qua ảnh khi nơi gọi quên truyền ground truth; mảng rỗng là ảnh không có object."""
    value = target.get(key)
    if value is None:
        if required:
            raise ValueError(f"target thiếu {key} (occlusion cần box ground truth đã map)")
        return np.zeros((0, 4), dtype=np.float64)
    boxes = np.asarray(value, dtype=np.float64)
    if boxes.size == 0:
        return np.zeros((0, 4), dtype=np.float64)
    if boxes.ndim != 2 or boxes.shape[1] != 4:
        raise ValueError(f"{key} phải có shape (K, 4), nhận {boxes.shape}")
    return boxes


def rectangle_size(
    box_w: float, box_h: float, ratio: float, max_w: int, max_h: int
) -> tuple[int, int]:
    """(w, h) nguyên, w ≤ max_w, h ≤ max_h, w·h gần `ratio`·box_w·box_h nhất, ưu tiên gần tỉ lệ
    box; (0, 0) khi không đặt được pixel nào."""
    target = ratio * box_w * box_h
    if target <= 0 or max_w < 1 or max_h < 1:
        return (0, 0)
    ideal_h = math.sqrt(target * box_h / box_w)
    best: tuple[float, float, int, int] | None = None
    for h in {math.floor(ideal_h), math.ceil(ideal_h)}:
        h = min(max(h, 1), max_h)
        for w in {math.floor(target / h), math.ceil(target / h)}:
            w = min(max(w, 1), max_w)
            key = (abs(w * h - target), abs(w / h - box_w / box_h), w, h)
            if best is None or key < best:
                best = key
    assert best is not None
    if best[0] >= target:  # không tô gì còn gần hơn (box quá nhỏ so với tỉ lệ)
        return (0, 0)
    return (best[2], best[3])


class OcclusionPerturbation:
    def __init__(self, spec: AttackSpec) -> None:
        if spec.kind != AttackKind.OCCLUSION or spec.primary_param.name != "occlusion_ratio":
            raise UnsupportedTransform(
                f"{spec.name}: cần kind = occlusion với tham số chính occlusion_ratio"
            )
        fill = spec.fixed_params.get("fill_255", DEFAULT_FILL_255)
        if not isinstance(fill, int) or not 0 <= fill <= 255:
            raise UnsupportedTransform(f"{spec.name}: fill_255 phải là số nguyên từ 0 đến 255")
        self.spec = spec
        self.fill = np.float32(fill / 255.0)

    def apply(
        self,
        images: ImageBatch,
        targets: list[dict[str, Any]],
        level: float,
        seed: int,
        mask: MaskBatch | None = None,
    ) -> ImageBatch:
        check_inputs(self.spec, images, targets, level, mask)
        result = images.copy()
        if level == 0:
            return result
        _, _, height, width = images.shape
        for i, target in enumerate(targets):
            rng = image_rng(seed, target_image_id(target, i))
            protected = self._protected(target, height, width)
            if mask is not None:
                protected |= mask[i, 0] == 0
            for x1, y1, x2, y2 in _boxes(target, "boxes", required=True):
                self._occlude(result[i], protected, (x1, y1, x2, y2), level, rng)
        return result

    @staticmethod
    def _protected(target: dict[str, Any], height: int, width: int) -> NDArray[np.bool_]:
        """Pixel chạm vào ignore region."""
        protected = np.zeros((height, width), dtype=bool)
        for x1, y1, x2, y2 in _boxes(target, "ignore_boxes", required=False):
            c0, c1 = max(0, math.floor(x1)), min(width, math.ceil(x2))
            r0, r1 = max(0, math.floor(y1)), min(height, math.ceil(y2))
            if c1 > c0 and r1 > r0:
                protected[r0:r1, c0:c1] = True
        return protected

    def _occlude(
        self,
        image: NDArray[np.float32],
        protected: NDArray[np.bool_],
        box: tuple[float, float, float, float],
        ratio: float,
        rng: np.random.Generator,
    ) -> None:
        _, height, width = image.shape
        x1, y1, x2, y2 = (
            max(0.0, box[0]),
            max(0.0, box[1]),
            min(width, box[2]),
            min(height, box[3]),
        )
        # Pixel nằm trọn trong box: cột [ceil(x1), floor(x2)), hàng [ceil(y1), floor(y2)).
        c0, c1 = math.ceil(x1), math.floor(x2)
        r0, r1 = math.ceil(y1), math.floor(y2)
        w, h = rectangle_size(x2 - x1, y2 - y1, ratio, c1 - c0, r1 - r0)
        if w == 0:
            return
        left = int(rng.integers(c0, c1 - w + 1))
        top = int(rng.integers(r0, r1 - h + 1))
        region = image[:, top : top + h, left : left + w]
        keep = protected[top : top + h, left : left + w]
        region[:, ~keep] = self.fill
