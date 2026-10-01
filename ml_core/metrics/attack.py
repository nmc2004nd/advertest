"""Metric sau tấn công (requirements.md Phase 2, mục Metric và Failure case).

Box xyxy pixel ảnh letterbox, label là chỉ số class trong model. Trước khi ghép, prediction được
lọc như pipeline mAP (`filter_classes`, `filter_ignored`): chỉ class đích, bỏ prediction nằm trong
ignore region. Ghép một-một được dùng cho cả ảnh sạch lẫn ảnh sau tấn công.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from numpy.typing import NDArray

from advertest_contracts.models import ClassRunMetrics, EvalMetrics, MapPair, RunMetrics
from ml_core.metrics.filters import Prediction, filter_classes, filter_ignored

IOU_THRESHOLD = 0.5
FP_WEIGHT = 0.5  # trọng số của new_false_positives trong severity_score


def iou(boxes: NDArray[Any], others: NDArray[Any]) -> NDArray[np.float64]:
    """IoU (N, M) giữa hai tập box xyxy. Hợp có diện tích 0 cho IoU = 0."""
    a = np.asarray(boxes, dtype=np.float64).reshape(-1, 4)
    b = np.asarray(others, dtype=np.float64).reshape(-1, 4)
    lt = np.maximum(a[:, None, :2], b[None, :, :2])
    rb = np.minimum(a[:, None, 2:], b[None, :, 2:])
    inter = np.clip(rb - lt, 0, None).prod(axis=2)
    area_a = np.clip(a[:, 2:] - a[:, :2], 0, None).prod(axis=1)
    area_b = np.clip(b[:, 2:] - b[:, :2], 0, None).prod(axis=1)
    union = area_a[:, None] + area_b[None, :] - inter
    out: NDArray[np.float64] = np.zeros(inter.shape, dtype=np.float64)
    np.divide(inter, union, out=out, where=union > 0)
    return out


@dataclass(frozen=True)
class Matching:
    gt_matched: NDArray[np.bool_]  # (G,)
    pred_matched: NDArray[
        np.bool_
    ]  # (K,) chỉ prediction có score >= operating_conf mới có thể True
    pred_confident: NDArray[np.bool_]  # (K,) score >= operating_conf


def match_predictions(
    pred: Prediction,
    target: Mapping[str, NDArray[Any]],
    operating_conf: float,
    iou_threshold: float = IOU_THRESHOLD,
) -> Matching:
    """Ghép một-một prediction với ground truth.

    Prediction có score >= `operating_conf` được duyệt theo score giảm dần (sắp xếp ổn định);
    mỗi prediction ghép với ground truth cùng class, chưa được ghép, có IoU lớn nhất và
    >= `iou_threshold`.
    """
    boxes = np.asarray(pred["boxes"]).reshape(-1, 4)
    labels = np.asarray(pred["labels"]).reshape(-1)
    scores = np.asarray(pred["scores"]).reshape(-1)
    gt_boxes = np.asarray(target["boxes"]).reshape(-1, 4)
    gt_labels = np.asarray(target["labels"]).reshape(-1)

    confident = np.asarray(scores >= operating_conf, dtype=bool)
    gt_matched = np.zeros(len(gt_boxes), dtype=bool)
    pred_matched = np.zeros(len(boxes), dtype=bool)
    if len(boxes) and len(gt_boxes):
        overlaps = iou(boxes, gt_boxes)
        for k in np.argsort(-scores, kind="stable"):
            if not confident[k]:
                continue
            candidates = (gt_labels == labels[k]) & ~gt_matched & (overlaps[k] >= iou_threshold)
            if not candidates.any():
                continue
            best = int(np.argmax(np.where(candidates, overlaps[k], -1.0)))
            gt_matched[best] = True
            pred_matched[k] = True
    return Matching(gt_matched=gt_matched, pred_matched=pred_matched, pred_confident=confident)


@dataclass(frozen=True)
class ImageAttackStats:
    correct: int  # |C| của ảnh: ground truth được detect đúng trên ảnh sạch
    lost: int  # object trong C không còn được detect đúng sau tấn công
    clean_fp: int
    attacked_fp: int
    # Phase 7: `correct`, `lost` theo label (chỉ số class trong model) để tính ASR theo class
    # (`ClassRunMetrics.attack_success_rate`); rỗng khi không tính theo class.
    class_correct: Mapping[int, int] = field(default_factory=dict)
    class_lost: Mapping[int, int] = field(default_factory=dict)

    @property
    def new_false_positives(self) -> int:
        return max(0, self.attacked_fp - self.clean_fp)

    @property
    def severity_score(self) -> float:
        return severity_score(self.lost, self.new_false_positives)


def _prepare(pred: Prediction, target_labels: Collection[int], ignore: NDArray[Any]) -> Prediction:
    return filter_ignored(filter_classes(pred, target_labels), ignore)


def image_attack_stats(
    clean: Prediction,
    attacked: Prediction,
    target: Mapping[str, NDArray[Any]],
    ignore_boxes: NDArray[Any],
    target_labels: Collection[int],
    operating_conf: float,
) -> ImageAttackStats:
    """Thống kê một ảnh từ prediction thô trên ảnh sạch và ảnh sau tấn công."""
    before = match_predictions(_prepare(clean, target_labels, ignore_boxes), target, operating_conf)
    after = match_predictions(
        _prepare(attacked, target_labels, ignore_boxes), target, operating_conf
    )
    lost = before.gt_matched & ~after.gt_matched
    gt_labels = np.asarray(target["labels"]).reshape(-1)
    return ImageAttackStats(
        correct=int(before.gt_matched.sum()),
        lost=int(lost.sum()),
        clean_fp=int((before.pred_confident & ~before.pred_matched).sum()),
        attacked_fp=int((after.pred_confident & ~after.pred_matched).sum()),
        class_correct=dict(Counter(int(label) for label in gt_labels[before.gt_matched])),
        class_lost=dict(Counter(int(label) for label in gt_labels[lost])),
    )


def attack_success_rate(stats: Iterable[ImageAttackStats]) -> float | None:
    """Số object mất / |C| trên cả slice; `None` khi |C| = 0."""
    items = list(stats)
    correct = sum(s.correct for s in items)
    if correct == 0:
        return None
    return sum(s.lost for s in items) / correct


def class_attack_success_rate(stats: Iterable[ImageAttackStats], label: int) -> float | None:
    """ASR chỉ tính object của class `label` (Phase 7); `None` khi không có object nào của class
    được detect đúng trên ảnh sạch."""
    items = list(stats)
    correct = sum(s.class_correct.get(label, 0) for s in items)
    if correct == 0:
        return None
    return sum(s.class_lost.get(label, 0) for s in items) / correct


def compute_drops(clean_map50: float, attacked_map50: float) -> tuple[float, float | None]:
    """(absolute_drop, relative_drop); relative_drop là `None` khi mAP@0.5 sạch bằng 0."""
    absolute = clean_map50 - attacked_map50
    relative = absolute / clean_map50 if clean_map50 != 0 else None
    return absolute, relative


def build_run_metrics(
    clean: EvalMetrics,
    attacked: EvalMetrics,
    stats: Iterable[ImageAttackStats],
    class_names: Sequence[str] | None = None,
) -> RunMetrics:
    """`RunMetrics` của contract từ mAP sạch, mAP sau tấn công và thống kê từng ảnh.

    `class_names` (`ModelCard.class_names`, Phase 7): có thì điền `per_class[*].attack_success_rate`
    từ `class_correct`, `class_lost` của thống kê."""
    if set(clean.per_class) != set(attacked.per_class):
        raise ValueError("clean và attacked phải cùng tập class đích")
    items = list(stats)
    absolute, relative = compute_drops(clean.map50, attacked.map50)
    labels = {name: i for i, name in enumerate(class_names)} if class_names is not None else None
    if labels is not None and set(clean.per_class) - set(labels):
        raise ValueError("class đích không có trong class_names của model")
    return RunMetrics(
        clean=MapPair(map50=clean.map50, map50_95=clean.map50_95),
        attacked=MapPair(map50=attacked.map50, map50_95=attacked.map50_95),
        relative_drop=relative,
        absolute_drop=absolute,
        attack_success_rate=attack_success_rate(items),
        per_class={
            name: ClassRunMetrics(
                clean_ap50=clean.per_class[name].ap50,
                attacked_ap50=attacked.per_class[name].ap50,
                attack_success_rate=(
                    None if labels is None else class_attack_success_rate(items, labels[name])
                ),
            )
            for name in sorted(clean.per_class)
        },
    )


def severity_score(lost_objects: int, new_false_positives: int) -> float:
    return lost_objects + FP_WEIGHT * new_false_positives


def select_failure_cases(
    stats_by_image: Mapping[str, ImageAttackStats], limit: int
) -> list[tuple[str, ImageAttackStats]]:
    """Tối đa `limit` ảnh có `severity_score > 0`, điểm giảm dần; cùng điểm thì `image_id` nhỏ
    hơn đứng trước."""
    if limit < 0:
        raise ValueError("limit phải >= 0")
    ranked = sorted(
        ((image_id, s) for image_id, s in stats_by_image.items() if s.severity_score > 0),
        key=lambda item: (-item[1].severity_score, item[0]),
    )
    return ranked[:limit]
