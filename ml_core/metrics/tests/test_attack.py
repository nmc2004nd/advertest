from collections.abc import Sequence
from typing import Any

import numpy as np
import pytest

from advertest_contracts.models import ClassEvalMetrics, EvalMetrics
from ml_core.metrics.attack import (
    ImageAttackStats,
    attack_success_rate,
    build_run_metrics,
    compute_drops,
    image_attack_stats,
    iou,
    match_predictions,
    select_failure_cases,
    severity_score,
)

CAR, PERSON, BIRD = 2, 0, 14
TARGETS = {CAR, PERSON}
CONF = 0.25
NO_IGNORE = np.zeros((0, 4), dtype=np.float32)

Row = tuple[Sequence[float], int, float]


def _pred(rows: list[Row]) -> dict[str, np.ndarray]:
    return {
        "boxes": np.asarray([r[0] for r in rows], dtype=np.float32).reshape(-1, 4),
        "labels": np.asarray([r[1] for r in rows], dtype=np.int64),
        "scores": np.asarray([r[2] for r in rows], dtype=np.float32),
    }


def _gt(rows: list[tuple[list[float], int]]) -> dict[str, np.ndarray]:
    return {
        "boxes": np.asarray([r[0] for r in rows], dtype=np.float32).reshape(-1, 4),
        "labels": np.asarray([r[1] for r in rows], dtype=np.int64),
    }


# 4 object tách rời nhau.
GT4 = _gt(
    [
        ([0, 0, 10, 10], CAR),
        ([20, 0, 30, 10], CAR),
        ([40, 0, 50, 10], PERSON),
        ([60, 0, 70, 10], PERSON),
    ]
)


def _hits(indices: list[int], score: float = 0.9) -> list[Row]:
    rows: list[Row] = []
    for i in indices:
        box = GT4["boxes"][i].tolist()
        rows.append(([box[0] + 0.5, box[1], box[2] + 0.5, box[3]], int(GT4["labels"][i]), score))
    return rows


def _stats(
    clean: Any, attacked: Any, target: Any = GT4, ignore: Any = NO_IGNORE
) -> ImageAttackStats:
    return image_attack_stats(clean, attacked, target, ignore, TARGETS, CONF)


def test_iou() -> None:
    values = iou(
        np.array([[0, 0, 10, 10]]), np.array([[0, 0, 10, 10], [5, 0, 15, 10], [20, 20, 30, 30]])
    )
    assert values[0] == pytest.approx([1.0, 50 / 150, 0.0])
    assert iou(np.array([[1, 1, 1, 1]]), np.array([[1, 1, 1, 1]]))[0, 0] == 0.0


def test_one_to_one_matching() -> None:
    gt = _gt([([0, 0, 10, 10], CAR)])
    pred = _pred([([0, 0, 10, 10], CAR, 0.6), ([0.5, 0, 10.5, 10], CAR, 0.9)])
    m = match_predictions(pred, gt, CONF)
    assert m.gt_matched.tolist() == [True]
    # Prediction score cao hơn được ghép trước; cái còn lại không được ghép.
    assert m.pred_matched.tolist() == [False, True]


def test_matching_prefers_highest_iou_and_same_class() -> None:
    gt = _gt([([0, 0, 10, 10], CAR), ([2, 0, 12, 10], CAR), ([0, 0, 10, 10], PERSON)])
    pred = _pred([([2, 0, 12, 10], CAR, 0.9)])
    m = match_predictions(pred, gt, CONF)
    assert m.gt_matched.tolist() == [False, True, False]


def test_low_score_is_not_in_c() -> None:
    gt = _gt([([0, 0, 10, 10], CAR)])
    low = _pred([([0, 0, 10, 10], CAR, 0.2)])
    assert match_predictions(low, gt, CONF).gt_matched.tolist() == [False]
    stats = _stats(low, low, target=gt)
    assert stats.correct == 0 and stats.clean_fp == 0
    assert match_predictions(
        _pred([([0, 0, 10, 10], CAR, 0.25)]), gt, CONF
    ).gt_matched.tolist() == [True]


def test_iou_threshold_is_inclusive_and_class_must_match() -> None:
    gt = _gt([([0, 0, 10, 10], CAR)])
    # IoU = 50 / 100... box [0, 0, 10, 5] có IoU 0.5 với gt.
    assert match_predictions(_pred([([0, 0, 10, 5], CAR, 0.9)]), gt, CONF).gt_matched.tolist() == [
        True
    ]
    assert match_predictions(_pred([([0, 0, 10, 4], CAR, 0.9)]), gt, CONF).gt_matched.tolist() == [
        False
    ]
    assert match_predictions(
        _pred([([0, 0, 10, 10], PERSON, 0.9)]), gt, CONF
    ).gt_matched.tolist() == [False]


def test_four_in_c_one_lost() -> None:
    stats = _stats(_pred(_hits([0, 1, 2, 3])), _pred(_hits([0, 1, 3])))
    assert (stats.correct, stats.lost) == (4, 1)
    assert attack_success_rate([stats]) == 0.25


def test_asr_zero_one_and_null() -> None:
    clean = _pred(_hits([0, 1, 2, 3]))
    assert attack_success_rate([_stats(clean, clean)]) == 0.0
    assert attack_success_rate([_stats(clean, _pred([]))]) == 1.0
    assert attack_success_rate([_stats(_pred([]), clean)]) is None
    assert attack_success_rate([]) is None


def test_asr_aggregates_over_images() -> None:
    a = _stats(_pred(_hits([0, 1, 2, 3])), _pred(_hits([0])))  # 4 trong C, mất 3
    b = _stats(_pred(_hits([0])), _pred(_hits([0])))  # 1 trong C, mất 0
    assert attack_success_rate([a, b]) == pytest.approx(3 / 5)


def test_object_missed_on_clean_is_not_lost() -> None:
    stats = _stats(_pred(_hits([0, 1])), _pred([]))
    assert (stats.correct, stats.lost) == (2, 2)


def test_one_box_covering_two_objects_saves_only_one() -> None:
    gt = _gt([([0, 0, 10, 10], CAR), ([1, 0, 11, 10], CAR)])
    clean = _pred([([0, 0, 10, 10], CAR, 0.9), ([1, 0, 11, 10], CAR, 0.8)])
    attacked = _pred([([0.5, 0, 10.5, 10], CAR, 0.9)])
    stats = _stats(clean, attacked, target=gt)
    assert (stats.correct, stats.lost) == (2, 1)


def test_new_false_positives_excludes_ignore_regions_and_other_classes() -> None:
    clean = _pred(_hits([0, 1, 2, 3]))
    ignore = np.asarray([[100, 100, 200, 200]], dtype=np.float32)
    attacked = _pred(
        [
            *_hits([0, 1, 2, 3]),
            ([300, 300, 320, 320], CAR, 0.9),  # FP mới
            ([120, 120, 150, 150], CAR, 0.9),  # trong ignore region
            ([400, 400, 420, 420], BIRD, 0.9),  # không phải class đích
            ([500, 500, 520, 520], CAR, 0.1),  # dưới operating_conf
        ]
    )
    stats = _stats(clean, attacked, ignore=ignore)
    assert stats.attacked_fp == 1 and stats.new_false_positives == 1


def test_new_false_positives_subtracts_clean_and_floors_at_zero() -> None:
    fp: list[Row] = [([300, 300, 320, 320], CAR, 0.9), ([330, 300, 350, 320], PERSON, 0.8)]
    clean = _pred(_hits([0, 1]) + fp)
    attacked_more = _pred(_hits([0, 1]) + fp + [([360, 300, 380, 320], CAR, 0.7)])
    assert _stats(clean, attacked_more).new_false_positives == 1
    attacked_fewer = _pred(_hits([0, 1]))
    stats = _stats(clean, attacked_fewer)
    assert stats.clean_fp == 2 and stats.new_false_positives == 0


def test_lost_object_prediction_shifted_counts_as_fp() -> None:
    # Box bị đẩy lệch hẳn khỏi object: object mất và prediction thành FP.
    clean = _pred(_hits([0]))
    attacked = _pred([([0, 30, 10, 40], CAR, 0.9)])
    stats = _stats(clean, attacked)
    assert (stats.lost, stats.new_false_positives) == (1, 1)
    assert stats.severity_score == 1.5


def test_compute_drops() -> None:
    absolute, relative = compute_drops(0.6, 0.45)
    assert absolute == pytest.approx(0.15) and relative == pytest.approx(0.25)
    assert compute_drops(0.0, 0.0) == (0.0, None)
    absolute, relative = compute_drops(0.4, 0.5)
    assert absolute == pytest.approx(-0.1) and relative == pytest.approx(-0.25)


def _eval(map50: float, car: float | None, person: float | None) -> EvalMetrics:
    def cls(ap: float | None) -> ClassEvalMetrics:
        return ClassEvalMetrics(
            ap50=ap, ap50_95=None if ap is None else ap / 2, num_gt=0 if ap is None else 3
        )

    return EvalMetrics(
        map50=map50, map50_95=map50 / 2, per_class={"car": cls(car), "person": cls(person)}
    )


def test_build_run_metrics() -> None:
    stats = [_stats(_pred(_hits([0, 1, 2, 3])), _pred(_hits([0, 1, 3])))]
    metrics = build_run_metrics(_eval(0.6, 0.7, None), _eval(0.3, 0.35, None), stats)
    assert metrics.clean.map50 == 0.6 and metrics.attacked.map50_95 == 0.15
    assert metrics.absolute_drop == pytest.approx(0.3) and metrics.relative_drop == pytest.approx(
        0.5
    )
    assert metrics.attack_success_rate == 0.25
    assert metrics.per_class is not None
    assert metrics.per_class["car"].attacked_ap50 == 0.35
    assert metrics.per_class["person"].clean_ap50 is None
    empty = build_run_metrics(_eval(0.0, 0.0, None), _eval(0.0, 0.0, None), [])
    assert empty.relative_drop is None and empty.attack_success_rate is None
    with pytest.raises(ValueError):
        build_run_metrics(
            _eval(0.6, 0.7, None),
            EvalMetrics(
                map50=0.3,
                map50_95=0.1,
                per_class={"car": ClassEvalMetrics(ap50=0.3, ap50_95=0.1, num_gt=3)},
            ),
            stats,
        )


def _s(lost: int, fp: int) -> ImageAttackStats:
    return ImageAttackStats(correct=lost, lost=lost, clean_fp=0, attacked_fp=fp)


def test_severity_score() -> None:
    assert severity_score(3, 1) == 3.5
    assert _s(2, 3).severity_score == 3.5


def test_select_failure_cases_order_limit_and_positive() -> None:
    stats = {
        "000010": _s(1, 0),
        "000002": _s(0, 0),  # điểm 0: bỏ
        "000007": _s(2, 0),
        "000003": _s(1, 2),  # cùng điểm 2.0 với 000007, id nhỏ hơn đứng trước
        "000001": _s(1, 0),
    }
    selected = select_failure_cases(stats, 10)
    assert [image_id for image_id, _ in selected] == ["000003", "000007", "000001", "000010"]
    assert [image_id for image_id, _ in select_failure_cases(stats, 2)] == ["000003", "000007"]
    assert select_failure_cases(stats, 0) == []
    reordered = dict(reversed(list(stats.items())))
    assert select_failure_cases(reordered, 10) == selected
    with pytest.raises(ValueError):
        select_failure_cases(stats, -1)
