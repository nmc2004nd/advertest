"""Nghiệm thu Phase 2, mục Metric (validation.md). Dữ liệu dựng sẵn, không cần model."""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from advertest_contracts.models import ClassEvalMetrics, EvalMetrics
from ml_core.metrics.attack import (
    attack_success_rate,
    build_run_metrics,
    compute_drops,
    image_attack_stats,
    match_predictions,
)

CAR, PERSON, BIRD = 2, 0, 14
TARGETS = {CAR, PERSON}
CONF = 0.25
NO_IGNORE = np.zeros((0, 4), np.float32)
GT = {
    "boxes": np.asarray(
        [[0, 0, 10, 10], [20, 0, 30, 10], [40, 0, 50, 10], [60, 0, 70, 10]], np.float32
    ),
    "labels": np.asarray([CAR, CAR, PERSON, PERSON], np.int64),
}


def _pred(rows: list[tuple[list[float], int, float]]) -> dict[str, np.ndarray]:
    return {
        "boxes": np.asarray([r[0] for r in rows], np.float32).reshape(-1, 4),
        "labels": np.asarray([r[1] for r in rows], np.int64),
        "scores": np.asarray([r[2] for r in rows], np.float32),
    }


def _hits(indices: list[int], score: float = 0.9) -> list[tuple[list[float], int, float]]:
    return [(GT["boxes"][i].tolist(), int(GT["labels"][i]), score) for i in indices]


def _stats(clean: Any, attacked: Any, ignore: Any = NO_IGNORE, target: Any = GT) -> Any:
    return image_attack_stats(clean, attacked, target, ignore, TARGETS, CONF)


def test_one_to_one_matching() -> None:
    target = {"boxes": GT["boxes"][:1], "labels": GT["labels"][:1]}
    pred = _pred([([0, 0, 10, 10], CAR, 0.9), ([0.5, 0, 10.5, 10], CAR, 0.8)])
    matching = match_predictions(pred, target, CONF)
    assert matching.gt_matched.sum() == 1 and matching.pred_matched.sum() == 1


def test_low_score_not_in_c() -> None:
    low = _pred(_hits([0, 1, 2, 3], score=0.2))
    assert _stats(low, low).correct == 0
    assert _stats(_pred(_hits([0, 1, 2, 3], score=0.25)), low).correct == 4


def test_four_in_c_one_lost() -> None:
    stats = _stats(_pred(_hits([0, 1, 2, 3])), _pred(_hits([0, 2, 3])))
    assert (stats.correct, stats.lost) == (4, 1)
    assert attack_success_rate([stats]) == 0.25


def test_nulls() -> None:
    assert attack_success_rate([_stats(_pred([]), _pred(_hits([0])))]) is None
    assert compute_drops(0.0, 0.0)[1] is None


def test_new_fp_in_ignore_region_not_counted() -> None:
    ignore = np.asarray([[100, 100, 200, 200]], np.float32)
    attacked = _pred([*_hits([0, 1, 2, 3]), ([120, 120, 150, 150], CAR, 0.9)])
    assert _stats(_pred(_hits([0, 1, 2, 3])), attacked, ignore).new_false_positives == 0
    outside = _pred([*_hits([0, 1, 2, 3]), ([300, 300, 330, 330], CAR, 0.9)])
    assert _stats(_pred(_hits([0, 1, 2, 3])), outside, ignore).new_false_positives == 1


def test_new_fp_subtracts_clean_and_is_at_least_zero() -> None:
    fp = [([300, 300, 330, 330], CAR, 0.9), ([400, 300, 430, 330], PERSON, 0.9)]
    clean = _pred([*_hits([0]), *fp])
    more = _pred([*_hits([0]), *fp, ([500, 300, 530, 330], CAR, 0.9)])
    assert _stats(clean, more).new_false_positives == 1
    assert _stats(clean, _pred(_hits([0]))).new_false_positives == 0


def test_non_target_class_is_not_a_false_positive() -> None:
    attacked = _pred([*_hits([0, 1, 2, 3]), ([300, 300, 330, 330], BIRD, 0.9)])
    assert _stats(_pred(_hits([0, 1, 2, 3])), attacked).new_false_positives == 0


def test_drops_formula() -> None:
    absolute, relative = compute_drops(0.6, 0.45)
    assert absolute == pytest.approx(0.15) and relative == pytest.approx(0.25)


def test_run_metrics_on_fixed_numbers() -> None:
    def metrics(map50: float) -> EvalMetrics:
        return EvalMetrics(
            map50=map50,
            map50_95=map50 / 2,
            per_class={"car": ClassEvalMetrics(ap50=map50, ap50_95=map50 / 2, num_gt=2)},
        )

    stats = [_stats(_pred(_hits([0, 1, 2, 3])), _pred(_hits([0, 2, 3])))]
    run = build_run_metrics(metrics(0.8), metrics(0.2), stats)
    assert run.absolute_drop == pytest.approx(0.6) and run.relative_drop == pytest.approx(0.75)
    assert run.attack_success_rate == 0.25
