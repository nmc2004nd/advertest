"""Tính một lượt thử nhanh (requirements.md Phase R2, mục Thử nhanh); không gọi HTTP.

1. Ảnh gốc → letterbox 640 và mask vùng ảnh thật; predict ảnh sạch.
2. Perturbation dựng một lần qua registry; mỗi level `apply` rồi predict. Thử nhanh không có
   ground truth nên attack nhận prediction sạch (score ≥ `operating_conf`) làm nhãn (người duyệt
   chốt ở Group 5).
3. Bảng object: chỉ xét detection có score ≥ `operating_conf`; ghép greedy theo IoU giảm dần,
   IoU ≥ 0.5 và cùng class. Object sạch không ghép được là `lost`, object chỉ có sau tấn công là
   `new`, còn lại là `kept`.
4. Ảnh trả về được làm mờ theo `rule_v1` như failure case Phase 6: ảnh sạch dùng vùng của detection
   sạch, ảnh mỗi level dùng vùng của detection sạch cộng detection sau tấn công. Ảnh chưa làm mờ
   không rời khỏi hàm này.
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from advertest_contracts.enums import QuickTryObjectStatus
from advertest_contracts.models import (
    AttackSpec,
    InferenceParams,
    QuickTryLevelReport,
    QuickTryObject,
)
from attacks.builders import BuildContext, PerturbationRegistry
from ml_core.metrics.attack import iou
from ml_core.models.adapter import ModelAdapter, Prediction
from ml_core.preprocess.letterbox import letterbox
from ml_core.privacy.blur import blur_regions
from ml_core.privacy.regions import Detection, rule_v1_regions
from ml_core.runner.images import letterbox_mask, png_bytes
from ml_core.runner.perturbations import gradient_estimator

MATCH_IOU = 0.5
SEED = 0
IMAGE_ID = "quick-try"


@dataclass(frozen=True)
class Box:
    """Một detection đã lọc theo `operating_conf` (xyxy letterbox)."""

    xyxy: tuple[float, float, float, float]
    class_name: str
    score: float


@dataclass(frozen=True)
class QuickTryOutput:
    clean_png: bytes  # đã làm mờ
    level_pngs: list[bytes]  # đã làm mờ, cùng thứ tự levels
    levels: list[QuickTryLevelReport]


def detections(pred: Prediction, class_names: Sequence[str], min_score: float) -> list[Box]:
    boxes = np.asarray(pred["boxes"], dtype=np.float64).reshape(-1, 4)
    labels, scores = np.asarray(pred["labels"]), np.asarray(pred["scores"], dtype=np.float64)
    return [
        Box(
            (float(b[0]), float(b[1]), float(b[2]), float(b[3])),
            class_names[int(label)],
            float(score),
        )
        for b, label, score in zip(boxes, labels, scores, strict=True)
        if score >= min_score
    ]


def match_objects(clean: Sequence[Box], attacked: Sequence[Box]) -> list[QuickTryObject]:
    """Ghép object sạch với object sau tấn công: greedy theo IoU giảm dần, IoU ≥ 0.5, cùng class.
    Thứ tự: object sạch theo thứ tự đầu vào (`kept` hoặc `lost`), rồi object `new`."""
    pairs: list[tuple[float, int, int]] = []
    if clean and attacked:
        overlaps = iou(np.array([b.xyxy for b in clean]), np.array([b.xyxy for b in attacked]))
        pairs = [
            (float(overlaps[i, j]), i, j)
            for i, c in enumerate(clean)
            for j, a in enumerate(attacked)
            if c.class_name == a.class_name and overlaps[i, j] >= MATCH_IOU
        ]
    pairs.sort(key=lambda p: (-p[0], p[1], p[2]))
    matched: dict[int, int] = {}
    used: set[int] = set()
    for _, i, j in pairs:
        if i not in matched and j not in used:
            matched[i] = j
            used.add(j)

    objects: list[QuickTryObject] = []
    for i, c in enumerate(clean):
        partner = matched.get(i)
        objects.append(
            QuickTryObject(
                bbox=c.xyxy,
                class_name=c.class_name,
                clean_score=c.score,
                attacked_score=attacked[partner].score if partner is not None else None,
                status=(
                    QuickTryObjectStatus.KEPT if partner is not None else QuickTryObjectStatus.LOST
                ),
            )
        )
    objects.extend(
        QuickTryObject(
            bbox=a.xyxy,
            class_name=a.class_name,
            clean_score=None,
            attacked_score=a.score,
            status=QuickTryObjectStatus.NEW,
        )
        for j, a in enumerate(attacked)
        if j not in used
    )
    return objects


def _detections(boxes: Sequence[Box]) -> list[Detection]:
    return [Detection(b.xyxy, b.class_name, b.score) for b in boxes]


def blurred_png(
    image: NDArray[np.float32], clean: Sequence[Box], attacked: Sequence[Box] = ()
) -> bytes:
    """PNG của ảnh (3, H, W) đã làm mờ vùng `rule_v1` của các detection."""
    _, height, width = image.shape
    regions = rule_v1_regions(
        ground_truth=[],
        clean=_detections(clean),
        attacked=_detections(attacked),
        ignore_boxes=[],
        width=width,
        height=height,
    )
    return png_bytes(blur_regions(image, regions))


def _targets(boxes: Sequence[Box], class_names: Sequence[str]) -> list[dict[str, Any]]:
    index = {name: i for i, name in enumerate(class_names)}
    return [
        {
            "boxes": np.array([b.xyxy for b in boxes], dtype=np.float32).reshape(-1, 4),
            "labels": np.array([index[b.class_name] for b in boxes], dtype=np.int64),
            "scores": np.array([b.score for b in boxes], dtype=np.float32),
            "image_id": IMAGE_ID,
            "ignore_boxes": np.zeros((0, 4), dtype=np.float32),
        }
    ]


def run_quick_try(
    image_bytes: bytes,
    adapter: ModelAdapter,
    spec: AttackSpec,
    levels: Sequence[float],
    params: InferenceParams,
    registry: PerturbationRegistry,
) -> QuickTryOutput:
    if spec.requires_training:
        raise ValueError(f"{spec.name} cần train patch, không dùng cho thử nhanh")
    if spec.requires_gradients and not adapter.capabilities.gradients:
        raise ValueError(f"{spec.name} cần gradient nhưng model không hỗ trợ gradient")
    with Image.open(io.BytesIO(image_bytes)) as source:
        image, info = letterbox(source, params.input_size)
    images = image[None]
    mask = letterbox_mask([info])
    names = adapter.class_names()

    clean = detections(adapter.predict(images, batch_size=1)[0], names, params.operating_conf)
    perturbation = registry.build(spec, BuildContext(estimator=gradient_estimator(adapter)))
    targets = _targets(clean, names)

    level_pngs: list[bytes] = []
    reports: list[QuickTryLevelReport] = []
    for level in levels:
        adversarial = perturbation.apply(images, targets, level, SEED, mask)
        pred = adapter.predict(adversarial, batch_size=1)[0]
        attacked = detections(pred, names, params.operating_conf)
        level_pngs.append(blurred_png(adversarial[0], clean, attacked))
        reports.append(QuickTryLevelReport(level=level, objects=match_objects(clean, attacked)))
    return QuickTryOutput(
        clean_png=blurred_png(image, clean), level_pngs=level_pngs, levels=reports
    )
