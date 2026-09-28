"""Nghiệm thu Phase 1, mục Metric (validation.md)."""

from __future__ import annotations

import numpy as np
import pytest
from torchmetrics.detection import MeanAveragePrecision

from advertest_contracts.models import ClassMapping, EvalMetrics, ModelCard
from ml_core.data.kitti import import_kitti
from ml_core.data.mapping import apply_mapping
from ml_core.metrics.clean import CleanMetric

from .conftest import KITTI_ROOT, Pipeline

Arrays = dict[str, np.ndarray]
NO_IGNORE = np.zeros((0, 4))
TARGETS = ["car", "person", "truck"]


@pytest.fixture(scope="module")
def names(pipeline: Pipeline) -> list[str]:
    return ModelCard.model_validate(pipeline.model).class_names


def _gt(boxes: list[list[float]], labels: list[int]) -> Arrays:
    return {
        "boxes": np.asarray(boxes, np.float32).reshape(-1, 4),
        "labels": np.asarray(labels, np.int64),
    }


def _pred(boxes: list[list[float]], labels: list[int], scores: list[float]) -> Arrays:
    return {**_gt(boxes, labels), "scores": np.asarray(scores, np.float32)}


def _compute(
    names: list[str], preds: list[Arrays], gts: list[Arrays], ignores: list[np.ndarray]
) -> EvalMetrics:
    metric = CleanMetric(names, TARGETS, max_det=300)
    metric.update(preds, gts, ignores)
    return metric.compute()


def _case(names: list[str]) -> tuple[list[Arrays], list[Arrays]]:
    car, person, truck = names.index("car"), names.index("person"), names.index("truck")
    gts = [
        _gt([[10, 10, 60, 60], [100, 100, 180, 220]], [car, person]),
        _gt([[300, 300, 400, 380]], [truck]),
    ]
    preds = [
        _pred(
            [[12, 10, 60, 62], [100, 100, 170, 200], [400, 400, 450, 450]],
            [car, person, car],
            [0.9, 0.6, 0.8],
        ),
        _pred([[300, 310, 400, 380], [0, 0, 20, 20]], [truck, person], [0.7, 0.95]),
    ]
    return preds, gts


def test_perfect_prediction_gives_map50_one(names: list[str]) -> None:
    _, gts = _case(names)
    preds = [{**g, "scores": np.ones(len(g["labels"]), np.float32)} for g in gts]
    assert _compute(names, preds, gts, [NO_IGNORE, NO_IGNORE]).map50 == pytest.approx(1.0)


def test_no_prediction_gives_map50_zero(names: list[str]) -> None:
    _, gts = _case(names)
    empty = _pred([], [], [])
    assert _compute(names, [empty, empty], gts, [NO_IGNORE, NO_IGNORE]).map50 == 0.0


def test_uses_torchmetrics_pycocotools_on_cpu(names: list[str]) -> None:
    metric = CleanMetric(names, TARGETS, max_det=300)
    # torchmetrics 1.9 không có thuộc tính công khai cho backend; đọc từ helper nội bộ.
    assert isinstance(metric._map, MeanAveragePrecision)
    assert metric._map._coco_backend.backend == "pycocotools"
    assert metric._map.device.type == "cpu"
    preds, gts = _case(names)
    metric.update(preds, gts, [NO_IGNORE, NO_IGNORE])
    assert 0 < metric.compute().map50 < 1


def test_prediction_inside_ignore_region_does_not_lower_map(names: list[str]) -> None:
    preds, gts = _case(names)
    base = _compute(names, preds, gts, [NO_IGNORE, NO_IGNORE])
    p0 = preds[0]
    extra = _pred(
        [*p0["boxes"].tolist(), [500, 10, 540, 50]],
        [*p0["labels"].tolist(), names.index("car")],
        [*p0["scores"].tolist(), 0.99],
    )
    with_ignore = _compute(
        names, [extra, preds[1]], gts, [np.array([[495, 5, 560, 60]]), NO_IGNORE]
    )
    assert with_ignore.map50 == pytest.approx(base.map50)
    assert with_ignore.map50_95 == pytest.approx(base.map50_95)


def test_prediction_of_unmapped_class_does_not_change_map(names: list[str]) -> None:
    preds, gts = _case(names)
    base = _compute(names, preds, gts, [NO_IGNORE, NO_IGNORE])
    p0 = preds[0]
    extra = _pred(
        [*p0["boxes"].tolist(), [10, 10, 60, 60]],
        [*p0["labels"].tolist(), names.index("traffic light")],
        [*p0["scores"].tolist(), 0.99],
    )
    assert _compute(names, [extra, preds[1]], gts, [NO_IGNORE, NO_IGNORE]) == base


def test_per_class_num_gt_on_fixture(names: list[str], pipeline: Pipeline) -> None:
    manifest = import_kitti(KITTI_ROOT)
    mapped = apply_mapping(manifest, ClassMapping.model_validate(pipeline.mapping))
    empty = _pred([], [], [])
    metric = CleanMetric(names, TARGETS, max_det=300)
    for img in mapped.values():
        labels = [names.index(c) for c in img.classes]
        metric.update([empty], [_gt(img.boxes.tolist(), labels)], [img.ignore_boxes])
    per_class = metric.compute().per_class
    assert set(per_class) == {"car", "truck", "person"}
    assert {k: v.num_gt for k, v in per_class.items()} == {"car": 14, "truck": 1, "person": 6}
