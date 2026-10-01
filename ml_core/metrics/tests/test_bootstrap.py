"""Bootstrap của tự tìm ngưỡng (validation.md Phase 7, mục "Đại lượng ngưỡng và bootstrap"; plan
task 11, 12)."""

from __future__ import annotations

import subprocess
import sys
from typing import Any
from uuid import UUID

import numpy as np
import pytest
from numpy.typing import NDArray

from advertest_contracts.enums import SearchStatus, ThresholdKind
from ml_core.metrics.bootstrap import (
    RECALL_THRESHOLDS,
    AttackEvidence,
    BootstrapPoint,
    EvalEvidence,
    _crossing,
    attack_evidence,
    average_precision_50,
    bootstrap_search,
    dump_run_predictions,
    evaluation_evidence,
    load_run_predictions,
    resample_weights,
    run_predictions_key,
)
from ml_core.metrics.clean import CleanMetric
from ml_core.metrics.filters import Prediction

CLASS_NAMES = ["person", "bicycle", "car", "motorcycle", "bus", "truck"]
TARGETS = [0, 2, 5]  # person, car, truck
MAX_DET = 300
CONF = 0.25


def _boxes(rng: np.random.Generator, n: int) -> NDArray[np.float32]:
    xy = rng.uniform(0, 560, size=(n, 2))
    wh = rng.uniform(8, 80, size=(n, 2))
    return np.concatenate([xy, xy + wh], axis=1).astype(np.float32)


def _scene(
    seed: int, n_images: int, quality: float
) -> tuple[list[str], dict[str, Any], dict[str, Prediction], dict[str, NDArray[Any]]]:
    """Ảnh ngẫu nhiên: ground truth, prediction (detect lại `quality` phần object, có lệch box,
    thêm false positive và class không phải class đích), ignore region ở vài ảnh."""
    rng = np.random.default_rng(seed)
    ids = [f"{i:06d}" for i in range(n_images)]
    targets: dict[str, Any] = {}
    preds: dict[str, Prediction] = {}
    ignore: dict[str, NDArray[Any]] = {}
    for image_id in ids:
        g = int(rng.integers(0, 6))
        gt_boxes = _boxes(rng, g)
        gt_labels = rng.choice([0, 2, 2, 5], size=g).astype(np.int64)
        if image_id.endswith("7"):
            gt_labels[:] = 2  # vài ảnh chỉ có car
        targets[image_id] = {"boxes": gt_boxes, "labels": gt_labels}
        keep = rng.random(g) < quality
        found = gt_boxes[keep] + rng.normal(0, 4, size=(int(keep.sum()), 4)).astype(np.float32)
        labels = gt_labels[keep].copy()
        swap = rng.random(len(labels)) < 0.1
        labels[swap] = 5
        fp_n = int(rng.integers(0, 4))
        boxes = np.concatenate([found, _boxes(rng, fp_n)]).astype(np.float32)
        labels = np.concatenate([labels, rng.choice([0, 1, 2, 5], size=fp_n)]).astype(np.int64)
        scores = rng.uniform(0.05, 1.0, size=len(boxes)).astype(np.float32)
        preds[image_id] = {"boxes": boxes, "labels": labels, "scores": scores}
        ignore[image_id] = (
            _boxes(rng, 1) if image_id.endswith("3") else np.zeros((0, 4), dtype=np.float32)
        )
    return ids, targets, preds, ignore


def _clean_metric(
    ids: list[str], targets: dict[str, Any], preds: dict[str, Prediction], ignore: dict[str, Any]
) -> tuple[float, dict[int, float | None]]:
    metric = CleanMetric(CLASS_NAMES, [CLASS_NAMES[i] for i in TARGETS], MAX_DET)
    metric.update([preds[i] for i in ids], [targets[i] for i in ids], [ignore[i] for i in ids])
    result = metric.compute()
    return result.map50, {label: result.per_class[CLASS_NAMES[label]].ap50 for label in TARGETS}


def _evidence(
    ids: list[str], targets: dict[str, Any], preds: dict[str, Prediction], ignore: dict[str, Any]
) -> EvalEvidence:
    return evaluation_evidence(preds, targets, ignore, ids, TARGETS, MAX_DET)


# ---------------------------------------------------------------- AP@0.5 khớp pycocotools


@pytest.mark.parametrize("seed", [0, 1, 3, 5, 7, 8])
def test_ap50_matches_clean_metric(seed: int) -> None:
    ids, targets, preds, ignore = _scene(seed, 40, quality=0.7)
    expected_map, expected_class = _clean_metric(ids, targets, preds, ignore)
    got_map, got_class = average_precision_50(_evidence(ids, targets, preds, ignore))
    assert got_map == pytest.approx(expected_map, abs=1e-9)
    for label in TARGETS:
        if expected_class[label] is None:
            assert got_class[label] is None
        else:
            assert got_class[label] == pytest.approx(expected_class[label], abs=1e-9)


def test_recall_thresholds_match_torchmetrics() -> None:
    import torch

    expected = np.asarray(torch.linspace(0.0, 1.0, 101).tolist())
    np.testing.assert_array_equal(RECALL_THRESHOLDS, expected)


def test_weights_equal_duplicated_images() -> None:
    ids, targets, preds, ignore = _scene(5, 25, quality=0.6)
    counts = np.random.default_rng(9).integers(0, 4, size=len(ids)).astype(np.int64)
    dup_ids, dup_targets, dup_preds, dup_ignore = [], {}, {}, {}
    for image_id, c in zip(ids, counts, strict=True):
        for copy in range(int(c)):
            key = f"{image_id}/{copy}"
            dup_ids.append(key)
            dup_targets[key], dup_preds[key] = targets[image_id], preds[image_id]
            dup_ignore[key] = ignore[image_id]
    expected_map, expected_class = _clean_metric(dup_ids, dup_targets, dup_preds, dup_ignore)
    got_map, got_class = average_precision_50(_evidence(ids, targets, preds, ignore), counts)
    assert got_map == pytest.approx(expected_map, abs=1e-6)
    for label in TARGETS:
        if expected_class[label] is not None:
            assert got_class[label] == pytest.approx(expected_class[label], abs=1e-6)


def test_class_without_ground_truth_is_none_and_excluded() -> None:
    ids, targets, preds, ignore = _scene(4, 10, quality=0.8)
    for image_id in ids:
        labels = targets[image_id]["labels"]
        targets[image_id] = {
            "boxes": targets[image_id]["boxes"][labels != 5],
            "labels": labels[labels != 5],
        }
    evidence = _evidence(ids, targets, preds, ignore)
    m, per_class = average_precision_50(evidence)
    assert per_class[5] is None
    known = [v for v in per_class.values() if v is not None]
    assert m == pytest.approx(sum(known) / len(known))


# ---------------------------------------------------------------- bootstrap


def _attack_scene(
    n: int, lost_fraction: float, seed: int
) -> tuple[list[str], dict[str, Any], dict[str, Prediction], dict[str, Prediction], dict[str, Any]]:
    """Ảnh sạch detect đúng mọi object; sau tấn công mất khoảng `lost_fraction` object."""
    rng = np.random.default_rng(seed)
    ids, targets, _, ignore = _scene(seed, n, quality=1.0)
    clean, attacked = {}, {}
    for image_id in ids:
        t = targets[image_id]
        clean[image_id] = {
            "boxes": t["boxes"].copy(),
            "labels": t["labels"].copy(),
            "scores": np.full(len(t["labels"]), 0.9, dtype=np.float32),
        }
        keep = rng.random(len(t["labels"])) >= lost_fraction
        attacked[image_id] = {
            "boxes": t["boxes"][keep],
            "labels": t["labels"][keep],
            "scores": np.full(int(keep.sum()), 0.9, dtype=np.float32),
        }
    return ids, targets, clean, attacked, ignore


def _point(
    order: int,
    level: float,
    ids: list[str],
    targets: dict[str, Any],
    clean: dict[str, Prediction],
    attacked: dict[str, Prediction],
    ignore: dict[str, Any],
) -> BootstrapPoint:
    return BootstrapPoint(
        order=order,
        level=level,
        attacked=_evidence(ids, targets, attacked, ignore),
        attack=attack_evidence(clean, attacked, targets, ignore, ids, TARGETS, CONF),
    )


def _search_points(
    fractions: list[float], n: int = 120, seed: int = 11
) -> tuple[EvalEvidence, list[BootstrapPoint], list[float]]:
    """Điểm toàn slice ở level 1, 2, ... với tỉ lệ mất tăng dần; trả cả đại lượng ASR điểm."""
    points, values = [], []
    clean_evidence = None
    for j, fraction in enumerate(fractions):
        ids, targets, clean, attacked, ignore = _attack_scene(n, fraction, seed + j)
        if clean_evidence is None:
            base_ids, base_targets, base_clean, _, base_ignore = ids, targets, clean, None, ignore
            clean_evidence = _evidence(base_ids, base_targets, base_clean, base_ignore)
        # mọi điểm dùng cùng ảnh sạch (cùng slice); chỉ prediction sau tấn công khác nhau
        rng = np.random.default_rng(100 + j)
        attacked = {}
        for image_id in base_ids:
            t = base_targets[image_id]
            keep = rng.random(len(t["labels"])) >= fraction
            attacked[image_id] = {
                "boxes": t["boxes"][keep],
                "labels": t["labels"][keep],
                "scores": np.full(int(keep.sum()), 0.9, dtype=np.float32),
            }
        point = _point(j, float(j + 1), base_ids, base_targets, base_clean, attacked, base_ignore)
        assert point.attack is not None
        values.append(point.attack.lost.sum() / point.attack.correct.sum())
        points.append(point)
    assert clean_evidence is not None
    return clean_evidence, points, values


def _run(
    clean: EvalEvidence,
    points: list[BootstrapPoint],
    status: SearchStatus,
    bracket: tuple[float, float],
    samples: int = 200,
    seed: int = 42,
    kind: ThresholdKind = ThresholdKind.ATTACK_SUCCESS_RATE,
    threshold: float = 0.3,
    label: int | None = None,
) -> Any:
    return bootstrap_search(
        clean=clean,
        points=points,
        threshold_kind=kind,
        threshold=threshold,
        class_label=label,
        status=status,
        bracket=bracket,
        samples=samples,
        seed=seed,
    )


def test_same_seed_same_intervals_and_zero_samples_is_null() -> None:
    clean, points, _ = _search_points([0.1, 0.25, 0.4, 0.7])
    first = _run(clean, points, SearchStatus.FOUND, (2.0, 3.0))
    again = _run(clean, points, SearchStatus.FOUND, (2.0, 3.0))
    assert first == again
    other = _run(clean, points, SearchStatus.FOUND, (2.0, 3.0), seed=7)
    assert other.drop_ci != first.drop_ci
    none = _run(clean, points, SearchStatus.FOUND, (2.0, 3.0), samples=0)
    assert (none.drop_ci, none.confidence_interval, none.near_threshold) == ({}, None, False)


@pytest.mark.parametrize(
    ("kind", "label"),
    [
        (ThresholdKind.ATTACK_SUCCESS_RATE, None),
        (ThresholdKind.ATTACK_SUCCESS_RATE, 2),
        (ThresholdKind.RELATIVE_DROP, None),
        (ThresholdKind.ABSOLUTE_DROP, 2),
    ],
)
def test_point_interval_contains_value_and_has_width(
    kind: ThresholdKind, label: int | None
) -> None:
    clean, points, _ = _search_points([0.1, 0.25, 0.4, 0.7])
    result = _run(clean, points, SearchStatus.FOUND, (2.0, 3.0), kind=kind, label=label)
    clean_map, clean_class = average_precision_50(clean)
    for point in points:
        assert point.attacked is not None and point.attack is not None
        if kind == ThresholdKind.ATTACK_SUCCESS_RATE:
            k = slice(None) if label is None else [TARGETS.index(label)]
            value = point.attack.lost[:, k].sum() / point.attack.correct[:, k].sum()
        else:
            attacked_map, attacked_class = average_precision_50(point.attacked)
            before = clean_map if label is None else clean_class[label]
            after = attacked_map if label is None else attacked_class[label]
            assert before is not None and after is not None
            value = (
                (before - after) / before if kind == ThresholdKind.RELATIVE_DROP else before - after
            )
        low, high = result.drop_ci[point.order]
        assert low <= value <= high
        assert high - low > 0


def test_breaking_point_interval_is_within_measured_levels() -> None:
    clean, points, values = _search_points([0.1, 0.25, 0.4, 0.7])
    assert values[1] < 0.3 <= values[2]
    result = _run(clean, points, SearchStatus.FOUND, (2.0, 3.0))
    assert result.confidence_interval is not None
    low, high = result.confidence_interval
    assert 1.0 <= low <= high <= 4.0
    assert low < 3.0 and high > 2.0


def test_synthetic_point_is_constant_zero() -> None:
    clean, points, _ = _search_points([0.1, 0.7])
    synthetic = BootstrapPoint(order=99, level=0.0, attacked=None, attack=None)
    result = _run(clean, [synthetic, *points], SearchStatus.FOUND, (0.0, 1.0), threshold=0.05)
    assert result.drop_ci[99] == (0.0, 0.0)


def test_near_threshold_when_barely_crossing() -> None:
    clean, points, values = _search_points([0.05, 0.35], n=60)
    threshold = values[1] - 0.005  # d(b) chỉ vượt ngưỡng rất ít
    assert values[0] < threshold <= values[1]
    near = _run(clean, points, SearchStatus.FOUND, (1.0, 2.0), threshold=threshold)
    assert near.near_threshold


def test_not_near_threshold_when_far() -> None:
    clean, points, values = _search_points([0.02, 0.9], n=120)
    threshold = (values[0] + values[1]) / 2
    far = _run(clean, points, SearchStatus.FOUND, (1.0, 2.0), threshold=threshold)
    assert not far.near_threshold


def test_near_threshold_for_not_reached_and_below_min() -> None:
    clean, points, values = _search_points([0.3], n=60)
    hi = (1.0, 1.0)
    assert _run(
        clean, points, SearchStatus.NOT_REACHED, hi, threshold=values[0] + 0.005
    ).near_threshold
    assert not _run(clean, points, SearchStatus.NOT_REACHED, hi, threshold=0.95).near_threshold
    assert _run(
        clean, points, SearchStatus.BELOW_MIN, hi, threshold=values[0] - 0.005
    ).near_threshold
    assert not _run(clean, points, SearchStatus.BELOW_MIN, hi, threshold=0.01).near_threshold


def test_no_breaking_point_interval_unless_found() -> None:
    clean, points, _ = _search_points([0.05, 0.1])
    result = _run(clean, points, SearchStatus.NOT_REACHED, (2.0, 2.0))
    assert result.confidence_interval is None
    assert result.drop_ci


def test_crossing_interpolates_and_censors_to_bounds() -> None:
    levels = np.asarray([0.0, 2.0, 4.0])
    assert _crossing(levels, np.asarray([0.0, 0.1, 0.3]), 0.2) == pytest.approx(3.0)
    assert _crossing(levels, np.asarray([0.0, 0.05, 0.1]), 0.2) == 4.0
    assert _crossing(levels, np.asarray([0.5, 0.6, 0.7]), 0.2) == 0.0
    assert _crossing(levels, np.asarray([0.0, 0.2, 0.1]), 0.2) == 2.0


def test_resample_weights_sum_to_slice_size() -> None:
    weights = resample_weights(30, 5, seed=1)
    assert weights.shape == (5, 30)
    assert (weights.sum(axis=1) == 30).all()
    assert (resample_weights(30, 5, seed=1) == weights).all()


def test_rejects_points_on_other_images_and_unknown_class() -> None:
    clean, points, _ = _search_points([0.1, 0.5], n=20)
    ids, targets, preds, ignore = _scene(3, 10, quality=0.5)
    stray = BootstrapPoint(5, 9.0, _evidence(ids, targets, preds, ignore), points[0].attack)
    with pytest.raises(ValueError):
        _run(clean, [*points, stray], SearchStatus.FOUND, (1.0, 2.0))
    with pytest.raises(ValueError):
        _run(clean, points, SearchStatus.FOUND, (1.0, 2.0), label=1)


def test_bootstrap_does_not_load_model() -> None:
    code = (
        "import sys, ml_core.metrics.bootstrap, ml_core.metrics.threshold; "
        "print(','.join(m for m in ('torch', 'ultralytics', 'art') if m in sys.modules))"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == ""


# ---------------------------------------------------------------- file prediction của run


def test_run_predictions_round_trip() -> None:
    run_id = UUID("8f0c0d2e-5e1b-4b8b-9a0e-1f2e3d4c5b6a")
    _, _, preds, _ = _scene(2, 4, quality=0.5)
    data = dump_run_predictions(run_id, preds, "cpu")
    loaded = load_run_predictions(data, run_id)
    assert run_predictions_key(run_id) == f"runs/{run_id}/predictions.json"
    assert set(loaded) == set(preds)
    for image_id, pred in preds.items():
        np.testing.assert_array_equal(loaded[image_id]["boxes"], pred["boxes"])
        np.testing.assert_array_equal(loaded[image_id]["labels"], pred["labels"])
        np.testing.assert_array_equal(loaded[image_id]["scores"], pred["scores"])
    with pytest.raises(ValueError):
        load_run_predictions(data, UUID(int=0))


def test_attack_evidence_matches_image_stats() -> None:
    ids, targets, clean, attacked, ignore = _attack_scene(15, 0.4, seed=3)
    evidence = attack_evidence(clean, attacked, targets, ignore, ids, TARGETS, CONF)
    assert isinstance(evidence, AttackEvidence)
    assert evidence.correct.shape == (15, len(TARGETS))
    assert (evidence.lost <= evidence.correct).all()
    assert evidence.lost.sum() > 0
