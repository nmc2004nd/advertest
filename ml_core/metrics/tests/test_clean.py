import json
from pathlib import Path

import numpy as np
import pytest
import torch
from torchmetrics.detection import MeanAveragePrecision

from advertest_contracts.hashing import sha256_of
from advertest_contracts.models import DatasetManifest, EvalMetrics
from ml_core.data.mapping import apply_mapping, build_mapping
from ml_core.data.tests.test_mapping_slice import model_card
from ml_core.metrics.clean import CleanMetric, max_detection_thresholds

# Một phần class COCO theo thứ tự index của YOLOv8.
CLASS_NAMES = [
    "person",
    "bicycle",
    "car",
    "motorcycle",
    "airplane",
    "bus",
    "train",
    "truck",
    "boat",
    "traffic light",
]
TARGETS = ["car", "person", "truck"]
PERSON, CAR, TRUCK, TRAFFIC_LIGHT = 0, 2, 7, 9
NO_IGNORE = np.zeros((0, 4))

Arrays = dict[str, np.ndarray]


def _gt(boxes: list[list[float]], labels: list[int]) -> Arrays:
    return {
        "boxes": np.asarray(boxes, dtype=np.float32).reshape(-1, 4),
        "labels": np.asarray(labels, dtype=np.int64),
    }


def _pred(boxes: list[list[float]], labels: list[int], scores: list[float]) -> Arrays:
    return {**_gt(boxes, labels), "scores": np.asarray(scores, dtype=np.float32)}


def _with_extra(pred: Arrays, box: list[float], label: int, score: float) -> Arrays:
    return _pred(
        [*pred["boxes"].tolist(), box],
        [*pred["labels"].tolist(), label],
        [*pred["scores"].tolist(), score],
    )


GT = [
    _gt([[10, 10, 60, 60], [100, 100, 180, 220]], [CAR, PERSON]),
    _gt([[300, 300, 400, 380]], [TRUCK]),
]
# Prediction không hoàn hảo để mAP nằm giữa 0 và 1.
IMPERFECT = [
    _pred(
        [[12, 10, 60, 62], [100, 100, 170, 200], [400, 400, 450, 450]],
        [CAR, PERSON, CAR],
        [0.9, 0.6, 0.8],
    ),
    _pred([[300, 310, 400, 380], [0, 0, 20, 20]], [TRUCK, PERSON], [0.7, 0.95]),
]


def _metric(max_det: int = 300) -> CleanMetric:
    return CleanMetric(CLASS_NAMES, TARGETS, max_det=max_det)


def _compute(preds: list[Arrays], ignores: list[np.ndarray] | None = None) -> EvalMetrics:
    m = _metric()
    m.update(preds, GT, ignores or [NO_IGNORE] * len(GT))
    return m.compute()


def test_perfect_predictions_give_map_one() -> None:
    preds = [{**g, "scores": np.ones(len(g["labels"]), dtype=np.float32)} for g in GT]
    result = _compute(preds)
    assert result.map50 == pytest.approx(1.0)
    assert result.map50_95 == pytest.approx(1.0)


def test_no_predictions_give_map_zero() -> None:
    empty = _pred([], [], [])
    result = _compute([empty, empty])
    assert result.map50 == 0.0 and result.map50_95 == 0.0
    assert all(c.ap50 == 0.0 for c in result.per_class.values())


def test_prediction_inside_ignore_region_does_not_lower_map() -> None:
    base = _compute(IMPERFECT)
    extra = [_with_extra(IMPERFECT[0], [500, 10, 540, 50], CAR, 0.99), IMPERFECT[1]]
    assert _compute(extra, [np.array([[495, 5, 560, 60]]), NO_IGNORE]) == base
    # Không có ignore region thì đó là false positive có score cao nhất: mAP giảm.
    assert _compute(extra).map50 < base.map50


def test_prediction_of_unmapped_class_does_not_change_map() -> None:
    base = _compute(IMPERFECT)
    extra = [_with_extra(IMPERFECT[0], [10, 10, 60, 60], TRAFFIC_LIGHT, 0.99), IMPERFECT[1]]
    assert _compute(extra) == base


def test_per_class_has_every_target_class() -> None:
    m = _metric()
    m.update([_pred([], [], [])], [_gt([[0, 0, 50, 50]], [CAR])], [NO_IGNORE])
    result = m.compute()
    assert set(result.per_class) == {"car", "person", "truck"}
    assert result.per_class["car"].num_gt == 1
    assert result.per_class["truck"].num_gt == 0 and result.per_class["truck"].ap50 is None


def test_class_without_gt_but_with_predictions_is_null() -> None:
    m = _metric()
    m.update(
        [_pred([[0, 0, 50, 50], [100, 100, 150, 150]], [CAR, TRUCK], [0.9, 0.9])],
        [_gt([[0, 0, 50, 50]], [CAR])],
        [NO_IGNORE],
    )
    result = m.compute()
    assert result.per_class["truck"].ap50 is None and result.per_class["truck"].ap50_95 is None
    assert result.per_class["car"].ap50 == pytest.approx(1.0)


def test_matches_torchmetrics_summary_when_max_det_is_100() -> None:
    """Công thức từ tensor precision trùng với số torchmetrics/pycocotools khi maxDets = 100."""
    ours = _metric(max_det=100)
    ours.update(IMPERFECT, GT, [NO_IGNORE, NO_IGNORE])
    result = ours.compute()

    ref = MeanAveragePrecision(
        box_format="xyxy", iou_type="bbox", class_metrics=True, backend="pycocotools"
    )
    ref.update(
        [{k: torch.as_tensor(v) for k, v in p.items()} for p in IMPERFECT],
        [{k: torch.as_tensor(v) for k, v in g.items()} for g in GT],
    )
    expected = ref.compute()
    assert 0 < result.map50 < 1
    assert result.map50 == pytest.approx(float(expected["map_50"]), abs=1e-6)
    assert result.map50_95 == pytest.approx(float(expected["map"]), abs=1e-6)
    classes, aps = expected["classes"].tolist(), expected["map_per_class"].tolist()
    for label, ap in zip(classes, aps, strict=True):
        assert result.per_class[CLASS_NAMES[label]].ap50_95 == pytest.approx(ap, abs=1e-6)


def test_max_det_limits_detections_per_image() -> None:
    # 12 false positive có score cao hơn prediction đúng: max_det = 10 cắt mất prediction đúng.
    fps = [[i * 20.0, 500.0, i * 20.0 + 10, 510.0] for i in range(12)]
    pred = _pred([*fps, [10, 10, 60, 60]], [CAR] * 13, [*([0.99] * 12), 0.5])
    gt = [_gt([[10, 10, 60, 60]], [CAR])]
    small, large = _metric(max_det=10), _metric(max_det=300)
    small.update([pred], gt, [NO_IGNORE])
    large.update([pred], gt, [NO_IGNORE])
    assert small.compute().map50 == 0.0
    assert large.compute().map50 > 0.0


def test_max_detection_thresholds() -> None:
    assert max_detection_thresholds(300) == [1, 10, 300]
    assert max_detection_thresholds(5) == [1, 5, 5]


def test_rejects_gt_outside_target_classes() -> None:
    m = _metric()
    with pytest.raises(ValueError, match="class đích"):
        m.update([_pred([], [], [])], [_gt([[0, 0, 5, 5]], [TRAFFIC_LIGHT])], [NO_IGNORE])


def test_rejects_unknown_target_class() -> None:
    with pytest.raises(ValueError):
        CleanMetric(CLASS_NAMES, ["car", "tram"], max_det=300)


def test_rejects_slice_without_ground_truth() -> None:
    m = _metric()
    m.update([_pred([], [], [])], [_gt([], [])], [NO_IGNORE])
    with pytest.raises(ValueError, match="ground truth"):
        m.compute()


def test_fixture_num_gt() -> None:
    """num_gt trên 5 ảnh fixture sau mapping kitti-coco và lọc Moderate."""
    path = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "manifest.json"
    manifest = DatasetManifest.model_validate(json.loads(path.read_text()))
    mapping = build_mapping(sha256_of(manifest), model_card(CLASS_NAMES), "kitti-coco")
    m = _metric()
    for img in apply_mapping(manifest, mapping).values():
        labels = [CLASS_NAMES.index(c) for c in img.classes]
        m.update([_pred([], [], [])], [_gt(img.boxes.tolist(), labels)], [img.ignore_boxes])
    per_class = m.compute().per_class
    assert {k: v.num_gt for k, v in per_class.items()} == {"car": 14, "truck": 1, "person": 6}
