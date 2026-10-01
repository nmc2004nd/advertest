"""Khoảng tin cậy bootstrap của tự tìm ngưỡng (requirements.md Phase 7, mục "Khoảng tin cậy
bootstrap"; plan task 11, 12).

Chỉ dùng các điểm toàn slice, từ prediction theo ảnh đã lưu (`RunResult.predictions_key`) và
prediction sạch trong cache: không gọi model.

- **Dữ liệu ghép trước** (`evaluation_evidence`, `attack_evidence`): mỗi detection (sau khi lọc
  class đích và ignore region như `CleanMetric`) được ghép với ground truth ở IoU 0.5 theo đúng
  quy tắc của COCO (`pycocotools.COCOeval.evaluateImg`); kèm số ground truth, số object đúng và
  mất theo class. Ghép theo từng ảnh nên một mẫu bootstrap chỉ cần trọng số theo ảnh.
- **AP@0.5 theo trọng số** (`average_precision_50`): nội suy 101 điểm recall như
  `COCOeval.accumulate`; với trọng số nguyên (số lần ảnh xuất hiện trong mẫu) cho cùng kết quả
  như chạy pycocotools trên tập ảnh lặp lại (test so với `CleanMetric`).
- **Mẫu bootstrap**: lấy lại có hoàn lại `n` ảnh của slice; cùng một mẫu dùng cho mọi điểm toàn
  slice. Seed suy từ seed của attack.
- **Điểm gãy của một mẫu**: level đầu tiên vượt ngưỡng bằng nội suy tuyến tính giữa hai điểm toàn
  slice liền kề. Mẫu không cắt ngưỡng được cắt về biên (quyết định Group 2): luôn dưới ngưỡng →
  level lớn nhất; gãy ngay ở điểm thấp nhất → level thấp nhất.
- **`near_threshold`** (quyết định Group 2): `found`/`non_monotonic` theo nguyên văn spec (KTC
  của `d(b)` có cận dưới < ngưỡng, hoặc KTC của `d(a)` có cận trên ≥ ngưỡng); `not_reached` chỉ
  xét `d(hi)` (cận trên ≥ ngưỡng); `below_min` chỉ xét `d(lo)` (cận dưới < ngưỡng); trạng thái
  khác là `false`.

File prediction theo ảnh của run (`runs/<run_id>/predictions.json`) cùng định dạng với
`cache/predictions` (box xyxy letterbox float32, label là chỉ số class trong model, prediction đã
lọc class đích nhưng chưa lọc ignore region); worker ghi và upload (Group 3).
"""

from __future__ import annotations

import json
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import numpy as np
from numpy.typing import NDArray

from advertest_contracts.enums import SearchStatus, ThresholdKind
from advertest_contracts.hashing import sha256_of
from ml_core.metrics.attack import image_attack_stats
from ml_core.metrics.filters import Prediction, filter_classes, filter_ignored
from ml_core.metrics.threshold import absolute, relative

IOU_50 = 0.5
# Ngưỡng recall như torchmetrics truyền cho COCOeval: `torch.linspace(0.0, 1.0, 101).tolist()`
# (float32, torch 2.14). Khác `np.linspace` ở chữ số cuối, đổi kết quả khi recall đúng bằng một
# phân số như 1/5. Ghi thẳng giá trị để không import torch; test so lại với torch.
RECALL_THRESHOLDS = np.asarray(
    [
        0.0,
        0.009999999776482582,
        0.019999999552965164,
        0.029999999329447746,
        0.03999999910593033,
        0.04999999701976776,
        0.05999999865889549,
        0.07000000029802322,
        0.07999999821186066,
        0.08999999612569809,
        0.09999999403953552,
        0.10999999940395355,
        0.11999999731779099,
        0.12999999523162842,
        0.14000000059604645,
        0.14999999105930328,
        0.1599999964237213,
        0.17000000178813934,
        0.17999999225139618,
        0.1899999976158142,
        0.19999998807907104,
        0.20999999344348907,
        0.2199999988079071,
        0.22999998927116394,
        0.23999999463558197,
        0.25,
        0.25999999046325684,
        0.26999998092651367,
        0.2800000011920929,
        0.28999999165534973,
        0.29999998211860657,
        0.3100000023841858,
        0.3199999928474426,
        0.32999998331069946,
        0.3400000035762787,
        0.3499999940395355,
        0.35999998450279236,
        0.3700000047683716,
        0.3799999952316284,
        0.38999998569488525,
        0.3999999761581421,
        0.4099999964237213,
        0.41999998688697815,
        0.429999977350235,
        0.4399999976158142,
        0.44999998807907104,
        0.4599999785423279,
        0.4699999988079071,
        0.47999998927116394,
        0.4899999797344208,
        0.5,
        0.5099999904632568,
        0.5199999809265137,
        0.5300000309944153,
        0.5400000214576721,
        0.550000011920929,
        0.5600000023841858,
        0.5699999928474426,
        0.5799999833106995,
        0.5900000333786011,
        0.6000000238418579,
        0.6100000143051147,
        0.6200000047683716,
        0.6299999952316284,
        0.6399999856948853,
        0.6500000357627869,
        0.6600000262260437,
        0.6700000166893005,
        0.6800000071525574,
        0.6899999976158142,
        0.699999988079071,
        0.7099999785423279,
        0.7200000286102295,
        0.7300000190734863,
        0.7400000095367432,
        0.75,
        0.7599999904632568,
        0.7699999809265137,
        0.7800000309944153,
        0.7900000214576721,
        0.800000011920929,
        0.8100000023841858,
        0.8199999928474426,
        0.8299999833106995,
        0.8400000333786011,
        0.8500000238418579,
        0.8600000143051147,
        0.8700000047683716,
        0.8799999952316284,
        0.8899999856948853,
        0.8999999761581421,
        0.9100000262260437,
        0.9200000166893005,
        0.9300000071525574,
        0.9399999976158142,
        0.949999988079071,
        0.9599999785423279,
        0.9700000286102295,
        0.9800000190734863,
        0.9900000095367432,
        1.0,
    ],
    dtype=np.float64,
)
CI_PERCENTILES = (2.5, 97.5)

Target = Mapping[str, NDArray[Any]]  # {"boxes": (G, 4), "labels": (G,)}


# ---------------------------------------------------------------- file prediction của run (task 11)


def run_predictions_key(run_id: UUID) -> str:
    """Khóa MinIO của `RunResult.predictions_key`."""
    return f"runs/{run_id}/predictions.json"


def dump_run_predictions(run_id: UUID, predictions: Mapping[str, Prediction], device: str) -> bytes:
    """JSON prediction theo `image_id` của một run (cùng định dạng `cache/predictions`)."""
    body = {
        image_id: {
            "boxes": np.asarray(p["boxes"], dtype=np.float32).reshape(-1, 4).tolist(),
            "labels": np.asarray(p["labels"], dtype=np.int64).tolist(),
            "scores": np.asarray(p["scores"], dtype=np.float32).tolist(),
        }
        for image_id, p in sorted(predictions.items())
    }
    data = {"key": run_predictions_key(run_id), "device": device, "predictions": body}
    return json.dumps(data, ensure_ascii=False).encode()


def load_run_predictions(data: bytes, run_id: UUID) -> dict[str, Prediction]:
    parsed = json.loads(data)
    if parsed.get("key") != run_predictions_key(run_id):
        raise ValueError(f"file prediction không thuộc run {run_id}")
    return {
        image_id: {
            "boxes": np.asarray(p["boxes"], dtype=np.float32).reshape(-1, 4),
            "labels": np.asarray(p["labels"], dtype=np.int64),
            "scores": np.asarray(p["scores"], dtype=np.float32),
        }
        for image_id, p in parsed["predictions"].items()
    }


# ---------------------------------------------------------------- dữ liệu ghép trước


@dataclass(frozen=True)
class ClassDetections:
    """Detection của một class trên mọi ảnh, sắp theo score giảm dần (ổn định theo thứ tự ảnh)."""

    tp: NDArray[np.bool_]
    image: NDArray[np.int64]


@dataclass(frozen=True)
class EvalEvidence:
    """Dữ liệu ghép ở IoU 0.5 của một tập prediction trên slice (ảnh theo `image_ids`)."""

    image_ids: tuple[str, ...]
    labels: tuple[int, ...]  # class đích (chỉ số trong model), tăng dần
    num_gt: NDArray[np.int64]  # (ảnh, class)
    detections: tuple[ClassDetections, ...]  # theo `labels`


@dataclass(frozen=True)
class AttackEvidence:
    """Số object đúng trên ảnh sạch và số bị mất sau tấn công, theo (ảnh, class)."""

    correct: NDArray[np.int64]
    lost: NDArray[np.int64]


def _xywh(boxes: NDArray[Any]) -> NDArray[np.float64]:
    """xyxy → xywh như torchmetrics (phép trừ trên float32) rồi đưa sang float64 như pycocotools."""
    b = np.asarray(boxes, dtype=np.float32).reshape(-1, 4)
    wh = b[:, 2:] - b[:, :2]
    return np.concatenate([b[:, :2], wh], axis=1).astype(np.float64)


def _iou(dt: NDArray[np.float64], gt: NDArray[np.float64]) -> NDArray[np.float64]:
    """IoU (D, G) của box xywh theo `maskApi.bbIou` của pycocotools (không crowd)."""
    w = np.minimum(dt[:, None, 0] + dt[:, None, 2], gt[None, :, 0] + gt[None, :, 2])
    w = w - np.maximum(dt[:, None, 0], gt[None, :, 0])
    h = np.minimum(dt[:, None, 1] + dt[:, None, 3], gt[None, :, 1] + gt[None, :, 3])
    h = h - np.maximum(dt[:, None, 1], gt[None, :, 1])
    inter = np.where((w > 0) & (h > 0), w * h, 0.0)
    union = (dt[:, 2] * dt[:, 3])[:, None] + (gt[:, 2] * gt[:, 3])[None, :] - inter
    out: NDArray[np.float64] = np.zeros(inter.shape, dtype=np.float64)
    np.divide(inter, union, out=out, where=union != 0)
    return out


AREA_ALL = (0.0, 1e5**2)  # COCOeval.Params.areaRng "all"


def _area(boxes: NDArray[np.float64]) -> NDArray[np.float64]:
    """Diện tích của box xywh (`bbox[2] * bbox[3]`, như torchmetrics và `COCO.loadRes`)."""
    area: NDArray[np.float64] = boxes[:, 2] * boxes[:, 3]
    return area


def _outside(area: NDArray[np.float64]) -> NDArray[np.bool_]:
    return np.asarray((area < AREA_ALL[0]) | (area > AREA_ALL[1]), dtype=bool)


def _match_coco(
    scores: NDArray[Any], boxes: NDArray[Any], gt_boxes: NDArray[Any], max_det: int
) -> tuple[NDArray[np.float64], NDArray[np.bool_], NDArray[np.bool_], int]:
    """Một (ảnh, class) theo `COCOeval.evaluateImg` ở IoU 0.5, vùng diện tích "all".

    Detection sắp theo score giảm dần (mergesort), giữ `max_det`. Ground truth có diện tích ngoài
    vùng (box suy biến, `x2 < x1`) bị bỏ qua và xếp sau. Mỗi detection ghép với ground truth chưa
    ghép có IoU lớn nhất ≥ 0.5 (bằng nhau thì lấy ground truth sau; đã ghép được ground truth
    thường thì không chuyển sang ground truth bị bỏ qua). Detection ghép với ground truth bị bỏ qua,
    hoặc không ghép được và có diện tích ngoài vùng, bị bỏ qua.

    Trả (score, tp, detection được tính, số ground truth không bị bỏ qua)."""
    gt = _xywh(gt_boxes)
    gt_ignore = _outside(_area(gt))
    gt_order = np.argsort(gt_ignore, kind="mergesort")
    gt, gt_ignore = gt[gt_order], gt_ignore[gt_order]
    order = np.argsort(-np.asarray(scores, dtype=np.float64), kind="mergesort")[:max_det]
    s = np.asarray(scores, dtype=np.float64)[order]
    dt = _xywh(boxes)[order]
    matched = np.full(len(order), -1, dtype=np.int64)
    if len(order) and len(gt):
        ious = _iou(dt, gt)
        taken = np.zeros(len(gt), dtype=bool)
        for d in range(len(order)):
            best, m = min(IOU_50, 1 - 1e-10), -1
            for g in range(len(gt)):
                if taken[g]:
                    continue
                if m > -1 and not gt_ignore[m] and gt_ignore[g]:
                    break
                if ious[d, g] < best:
                    continue
                best, m = ious[d, g], g
            if m >= 0:
                taken[m] = True
                matched[d] = m
    is_matched = matched >= 0
    ignored = _outside(_area(dt))
    if is_matched.any():
        ignored[is_matched] = gt_ignore[matched[is_matched]]
    return s, is_matched, ~ignored, int((~gt_ignore).sum())


def evaluation_evidence(
    predictions: Mapping[str, Prediction],
    targets: Mapping[str, Target],
    ignore_boxes: Mapping[str, NDArray[Any]],
    image_ids: Sequence[str],
    target_labels: Collection[int],
    max_det: int,
) -> EvalEvidence:
    """Ghép trước của một tập prediction thô (chưa lọc) trên slice."""
    labels = tuple(sorted(int(label) for label in target_labels))
    num_gt = np.zeros((len(image_ids), len(labels)), dtype=np.int64)
    per_class: list[list[tuple[NDArray[np.float64], NDArray[np.bool_], int]]] = [[] for _ in labels]
    for i, image_id in enumerate(image_ids):
        kept = filter_ignored(filter_classes(predictions[image_id], labels), ignore_boxes[image_id])
        gt_boxes = np.asarray(targets[image_id]["boxes"], dtype=np.float32).reshape(-1, 4)
        gt_labels = np.asarray(targets[image_id]["labels"], dtype=np.int64).reshape(-1)
        dt_boxes = np.asarray(kept["boxes"]).reshape(-1, 4)
        dt_labels = np.asarray(kept["labels"]).reshape(-1)
        dt_scores = np.asarray(kept["scores"]).reshape(-1)
        for k, label in enumerate(labels):
            dt = dt_labels == label
            s, tp, counted, npig = _match_coco(
                dt_scores[dt], dt_boxes[dt], gt_boxes[gt_labels == label], max_det
            )
            num_gt[i, k] = npig
            per_class[k].append((s[counted], tp[counted], i))
    detections = []
    for items in per_class:
        scores = np.concatenate([s for s, _, _ in items]) if items else np.zeros(0)
        tps = np.concatenate([tp for _, tp, _ in items]) if items else np.zeros(0, dtype=bool)
        image = np.concatenate([np.full(len(s), i, dtype=np.int64) for s, _, i in items])
        order = np.argsort(-scores, kind="mergesort")
        detections.append(ClassDetections(tp=tps[order], image=image[order]))
    return EvalEvidence(tuple(image_ids), labels, num_gt, tuple(detections))


def attack_evidence(
    clean: Mapping[str, Prediction],
    attacked: Mapping[str, Prediction],
    targets: Mapping[str, Target],
    ignore_boxes: Mapping[str, NDArray[Any]],
    image_ids: Sequence[str],
    target_labels: Collection[int],
    operating_conf: float,
) -> AttackEvidence:
    """Số object đúng và mất theo (ảnh, class), cùng quy tắc với `image_attack_stats`."""
    labels = sorted(int(label) for label in target_labels)
    correct = np.zeros((len(image_ids), len(labels)), dtype=np.int64)
    lost = np.zeros_like(correct)
    for i, image_id in enumerate(image_ids):
        stats = image_attack_stats(
            clean[image_id],
            attacked[image_id],
            targets[image_id],
            ignore_boxes[image_id],
            labels,
            operating_conf,
        )
        for k, label in enumerate(labels):
            correct[i, k] = stats.class_correct.get(label, 0)
            lost[i, k] = stats.class_lost.get(label, 0)
    return AttackEvidence(correct, lost)


# ---------------------------------------------------------------- AP@0.5 theo trọng số


def _class_ap(det: ClassDetections, weights: NDArray[np.int64], npig: int) -> float:
    if len(det.tp) == 0:
        return 0.0
    w = weights[det.image]
    tp = np.cumsum(w * det.tp)
    fp = np.cumsum(w * ~det.tp)
    recall = tp / npig
    precision = tp / (tp + fp + np.spacing(1))
    envelope = np.maximum.accumulate(precision[::-1])[::-1]
    index = np.searchsorted(recall, RECALL_THRESHOLDS, side="left")
    q = np.where(index < len(recall), envelope[np.minimum(index, len(recall) - 1)], 0.0)
    return float(q.mean())


def average_precision_50(
    evidence: EvalEvidence, weights: NDArray[np.int64] | None = None
) -> tuple[float, dict[int, float | None]]:
    """(mAP@0.5, AP@0.5 theo class) với trọng số nguyên theo ảnh (mặc định 1). Class không có
    ground truth có AP `None` và không tính vào mAP (như `CleanMetric`); không class nào có
    ground truth thì mAP là 0."""
    w = np.ones(len(evidence.image_ids), dtype=np.int64) if weights is None else weights
    per_class: dict[int, float | None] = {}
    for k, label in enumerate(evidence.labels):
        npig = int((w * evidence.num_gt[:, k]).sum())
        per_class[label] = None if npig == 0 else _class_ap(evidence.detections[k], w, npig)
    known = [ap for ap in per_class.values() if ap is not None]
    return (float(np.mean(known)) if known else 0.0), per_class


# ---------------------------------------------------------------- bootstrap


@dataclass(frozen=True)
class BootstrapPoint:
    """Một điểm toàn slice của quỹ đạo; `attacked`/`attack` null với điểm synthetic (level 0,
    đại lượng bằng 0)."""

    order: int
    level: float
    attacked: EvalEvidence | None
    attack: AttackEvidence | None


@dataclass(frozen=True)
class BootstrapResult:
    drop_ci: dict[int, tuple[float, float]]  # theo `TrajectoryPoint.order`
    confidence_interval: tuple[float, float] | None
    near_threshold: bool


def bootstrap_rng(seed: int) -> np.random.Generator:
    """Bộ sinh số của bootstrap, suy từ seed của attack (tách khỏi seed theo ảnh và tập con)."""
    return np.random.default_rng(int(sha256_of({"purpose": "bootstrap", "seed": seed})[:16], 16))


def resample_weights(n_images: int, samples: int, seed: int) -> NDArray[np.int64]:
    """(samples, n_images): số lần mỗi ảnh xuất hiện trong từng mẫu lấy lại có hoàn lại."""
    draws = bootstrap_rng(seed).integers(0, n_images, size=(samples, n_images))
    counts = np.zeros((samples, n_images), dtype=np.int64)
    np.add.at(counts, (np.arange(samples)[:, None], draws), 1)
    return counts


def _quantity(
    kind: ThresholdKind,
    label: int | None,
    clean: EvalEvidence,
    point: BootstrapPoint,
    weights: NDArray[np.int64],
    clean_ap: tuple[float, dict[int, float | None]],
) -> float:
    """Đại lượng so với ngưỡng trên một mẫu; NaN khi không tính được."""
    if point.attacked is None or point.attack is None:
        return 0.0
    if kind == ThresholdKind.ATTACK_SUCCESS_RATE:
        column = slice(None) if label is None else [clean.labels.index(label)]
        correct = int((weights[:, None] * point.attack.correct[:, column]).sum())
        lost = int((weights[:, None] * point.attack.lost[:, column]).sum())
        return float("nan") if correct == 0 else lost / correct
    attacked_map, attacked_class = average_precision_50(point.attacked, weights)
    clean_map, clean_class = clean_ap
    before, after = (
        (clean_map, attacked_map) if label is None else (clean_class[label], attacked_class[label])
    )
    if label is None and not any(v is not None for v in clean_class.values()):
        return float("nan")
    value = (relative if kind == ThresholdKind.RELATIVE_DROP else absolute)(before, after)
    return float("nan") if value is None else value


def _crossing(levels: NDArray[np.float64], drops: NDArray[np.float64], threshold: float) -> float:
    """Level đầu tiên vượt ngưỡng (nội suy tuyến tính), cắt về biên khi không cắt ngưỡng."""
    if drops[0] >= threshold:
        return float(levels[0])
    for i in range(len(levels) - 1):
        if drops[i] < threshold <= drops[i + 1]:
            fraction = (threshold - drops[i]) / (drops[i + 1] - drops[i])
            return float(levels[i] + fraction * (levels[i + 1] - levels[i]))
    return float(levels[-1])


def _interval(values: NDArray[np.float64]) -> tuple[float, float] | None:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return None
    low, high = np.percentile(finite, CI_PERCENTILES)
    return float(low), float(high)


def bootstrap_search(
    *,
    clean: EvalEvidence,
    points: Sequence[BootstrapPoint],
    threshold_kind: ThresholdKind,
    threshold: float,
    class_label: int | None,
    status: SearchStatus,
    bracket: tuple[float, float],
    samples: int,
    seed: int,
) -> BootstrapResult:
    """KTC 95% của đại lượng ở từng điểm toàn slice và của điểm gãy; `samples = 0` hoặc không
    có điểm toàn slice → mọi giá trị null."""
    if samples < 0:
        raise ValueError("samples phải không âm")
    if class_label is not None and class_label not in clean.labels:
        raise ValueError(f"class {class_label} không phải class đích")
    for point in points:
        if point.attacked is not None and point.attacked.image_ids != clean.image_ids:
            raise ValueError("mọi điểm phải đánh giá đúng các ảnh của slice, cùng thứ tự")
    if samples == 0 or not points:
        return BootstrapResult({}, None, False)

    weights = resample_weights(len(clean.image_ids), samples, seed)
    ordered = sorted(points, key=lambda p: (p.level, p.order))
    drops = np.empty((samples, len(ordered)), dtype=np.float64)
    for b in range(samples):
        clean_ap = average_precision_50(clean, weights[b])
        for j, point in enumerate(ordered):
            drops[b, j] = _quantity(threshold_kind, class_label, clean, point, weights[b], clean_ap)

    drop_ci: dict[int, tuple[float, float]] = {}
    for j, point in enumerate(ordered):
        interval = _interval(drops[:, j])
        if interval is not None:
            drop_ci[point.order] = interval

    confidence = None
    if status in (SearchStatus.FOUND, SearchStatus.NON_MONOTONIC):
        levels = np.asarray([p.level for p in ordered], dtype=np.float64)
        complete = np.isfinite(drops).all(axis=1)
        crossings = np.asarray(
            [_crossing(levels, row, threshold) for row in drops[complete]], dtype=np.float64
        )
        confidence = _interval(crossings)

    by_level = {p.level: drop_ci.get(p.order) for p in ordered}
    low_ci, high_ci = by_level.get(bracket[0]), by_level.get(bracket[1])
    near = False
    if status in (SearchStatus.FOUND, SearchStatus.NON_MONOTONIC):
        near = (high_ci is not None and high_ci[0] < threshold) or (
            low_ci is not None and low_ci[1] >= threshold
        )
    elif status == SearchStatus.NOT_REACHED:
        near = high_ci is not None and high_ci[1] >= threshold
    elif status == SearchStatus.BELOW_MIN:
        near = low_ci is not None and low_ci[0] < threshold
    return BootstrapResult(drop_ci, confidence, near)
