import numpy as np
import pytest

from ml_core.metrics.filters import filter_classes, filter_ignored, ioa


def _pred(boxes: list[list[float]], labels: list[int]) -> dict[str, np.ndarray]:
    return {
        "boxes": np.asarray(boxes, dtype=np.float32).reshape(-1, 4),
        "labels": np.asarray(labels, dtype=np.int64),
        "scores": np.linspace(0.9, 0.5, len(labels)).astype(np.float32),
    }


def test_filter_classes_keeps_only_target_classes() -> None:
    # car, traffic light, person
    pred = _pred([[0, 0, 10, 10], [5, 5, 20, 20], [1, 1, 3, 3]], [2, 9, 0])
    out = filter_classes(pred, {0, 2, 7})
    assert out["labels"].tolist() == [2, 0]
    assert out["boxes"].shape == (2, 4) and out["scores"].tolist() == pytest.approx([0.9, 0.5])


def test_ioa_is_relative_to_prediction_area() -> None:
    values = ioa(np.array([[0, 0, 10, 10], [0, 0, 100, 100]]), np.array([[0, 0, 10, 20]]))
    # Giao 10 x 20 = 200 trên diện tích prediction 10 000.
    assert values[:, 0] == pytest.approx([1.0, 0.02])


def test_ioa_zero_area_box() -> None:
    assert ioa(np.array([[5, 5, 5, 10]]), np.array([[0, 0, 10, 10]]))[0, 0] == 0.0


def test_filter_ignored_threshold_inclusive() -> None:
    region = np.array([[0, 0, 10, 10]])
    pred = _pred([[0, 0, 10, 10], [5, 0, 15, 10], [6, 0, 16, 10], [20, 20, 30, 30]], [2, 2, 2, 2])
    # IoA: 1.0, 0.5 (bị loại, tính cả biên), 0.4, 0.
    out = filter_ignored(pred, region)
    assert out["boxes"].tolist() == [[6, 0, 16, 10], [20, 20, 30, 30]]


def test_filter_ignored_without_regions_or_predictions() -> None:
    pred = _pred([[0, 0, 10, 10]], [2])
    assert len(filter_ignored(pred, np.zeros((0, 4)))["labels"]) == 1
    assert len(filter_ignored(_pred([], []), np.array([[0, 0, 5, 5]]))["labels"]) == 0
