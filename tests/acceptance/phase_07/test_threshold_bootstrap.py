"""validation.md Phase 7, Đại lượng ngưỡng và bootstrap (`test_threshold_bootstrap.py`).

Phần không cần DB dùng số liệu dựng sẵn: 40 ảnh, mỗi ảnh một object `person` (label 0) và một
`car` (label 2); prediction sạch trùng ground truth. Ở level `L`, các ảnh có chỉ số trong một tập
cố định (tỉ lệ `LOST[L]`) mất detection `person`: mức sụt AP@0.5 của person bằng đúng tỉ lệ đó,
khác nhau giữa các ảnh nên bootstrap có biến thiên. Mục "không gọi model" chạy worker thật
(`test_search_e2e_backend.py` dùng cùng hạ tầng) nên có marker `db`.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from advertest_contracts.enums import SearchStatus, ThresholdKind
from advertest_contracts.models import (
    ClassRunMetrics,
    MapPair,
    PrimaryParam,
    RunMetrics,
    SearchConfig,
)
from ml_core.metrics.bootstrap import (
    BootstrapPoint,
    attack_evidence,
    average_precision_50,
    bootstrap_search,
    evaluation_evidence,
)
from ml_core.metrics.filters import Prediction
from ml_core.metrics.threshold import threshold_quantity
from ml_core.search.algorithm import Observation, ThresholdSearch

N = 40
PERSON, CAR = 0, 2
LABELS = {PERSON, CAR}
IDS = [f"img{i:03d}" for i in range(N)]
BOX_PERSON = [10.0, 10.0, 60.0, 120.0]
BOX_CAR = [200.0, 50.0, 400.0, 150.0]
NO_IGNORE = {i: np.zeros((0, 4), dtype=np.float32) for i in IDS}
TARGETS = {
    i: {"boxes": np.asarray([BOX_PERSON, BOX_CAR], np.float32), "labels": np.asarray([0, 2])}
    for i in IDS
}
MAX_DET, CONF = 100, 0.25
# Thứ tự mất detection cố định (ảnh nào mất trước), trộn để không theo chỉ số.
ORDER = list(np.random.default_rng(3).permutation(N))


def _pred(person: bool) -> Prediction:
    boxes = ([BOX_PERSON] if person else []) + [BOX_CAR]
    labels = ([PERSON] if person else []) + [CAR]
    return {
        "boxes": np.asarray(boxes, np.float32).reshape(-1, 4),
        "labels": np.asarray(labels, np.int64),
        "scores": np.full(len(labels), 0.9, np.float32),
    }


CLEAN = {i: _pred(True) for i in IDS}


def attacked(lost_fraction: float) -> dict[str, Prediction]:
    lost = {IDS[k] for k in ORDER[: round(lost_fraction * N)]}
    return {i: _pred(i not in lost) for i in IDS}


def evidence() -> Any:
    return evaluation_evidence(CLEAN, TARGETS, NO_IGNORE, IDS, LABELS, MAX_DET)


def point(order: int, level: float, lost_fraction: float) -> BootstrapPoint:
    preds = attacked(lost_fraction)
    return BootstrapPoint(
        order,
        level,
        evaluation_evidence(preds, TARGETS, NO_IGNORE, IDS, LABELS, MAX_DET),
        attack_evidence(CLEAN, preds, TARGETS, NO_IGNORE, IDS, LABELS, CONF),
    )


# ---------------------------------------------------------------- đại lượng so với ngưỡng


METRICS = RunMetrics(
    clean=MapPair(map50=0.8, map50_95=0.5),
    attacked=MapPair(map50=0.6, map50_95=0.3),
    relative_drop=0.25,
    absolute_drop=0.2,
    attack_success_rate=0.4,
    per_class={
        "person": ClassRunMetrics(clean_ap50=0.5, attacked_ap50=0.2, attack_success_rate=0.7),
        "car": ClassRunMetrics(clean_ap50=0.9, attacked_ap50=0.9, attack_success_rate=0.0),
    },
)


@pytest.mark.parametrize(
    ("kind", "class_filter", "expected"),
    [
        (ThresholdKind.RELATIVE_DROP, None, (0.8 - 0.6) / 0.8),
        (ThresholdKind.ABSOLUTE_DROP, None, 0.8 - 0.6),
        (ThresholdKind.ATTACK_SUCCESS_RATE, None, 0.4),
        (ThresholdKind.RELATIVE_DROP, "person", (0.5 - 0.2) / 0.5),
        (ThresholdKind.ABSOLUTE_DROP, "person", 0.5 - 0.2),
        (ThresholdKind.ATTACK_SUCCESS_RATE, "person", 0.7),
        (ThresholdKind.RELATIVE_DROP, "car", 0.0),
    ],
)
def test_threshold_quantity(kind: ThresholdKind, class_filter: str | None, expected: float) -> None:
    assert threshold_quantity(METRICS, kind, class_filter) == pytest.approx(expected)


EPS = PrimaryParam(name="eps", type="continuous", min=0, max=32, unit="1/255")


def _first_point_fails(kind: ThresholdKind, class_filter: str | None, metrics: RunMetrics) -> Any:
    """Thuật toán nhận đại lượng của điểm đầu tiên (không tính được) và phải kết thúc `failed`."""
    config = SearchConfig(threshold_kind=kind, threshold=0.2, lo=0, hi=32, tol=0.5,
                          class_filter=class_filter)  # fmt: skip
    search = ThresholdSearch(config, EPS, 300)
    first = search.progress([]).next_point
    assert first is not None
    drop = threshold_quantity(metrics, kind, class_filter)
    assert drop is None
    return search.progress([Observation(first.level, first.scope, drop)])


def test_zero_clean_map_with_relative_drop_fails_with_message() -> None:
    zero = METRICS.model_copy(
        update={"clean": MapPair(map50=0.0, map50_95=0.0), "relative_drop": None}
    )
    progress = _first_point_fails(ThresholdKind.RELATIVE_DROP, None, zero)
    assert progress.status == SearchStatus.FAILED
    assert progress.message


@pytest.mark.parametrize("class_filter", [None, "person"])
def test_no_correct_object_with_asr_fails_with_message(class_filter: str | None) -> None:
    none = METRICS.model_copy(
        update={
            "attack_success_rate": None,
            "per_class": {"person": ClassRunMetrics(clean_ap50=0.0, attacked_ap50=0.0)},
        }
    )
    progress = _first_point_fails(ThresholdKind.ATTACK_SUCCESS_RATE, class_filter, none)
    assert progress.status == SearchStatus.FAILED
    assert progress.message


# ---------------------------------------------------------------- bootstrap


def _run(points: list[BootstrapPoint], *, samples: int = 200, seed: int = 0,
         status: SearchStatus = SearchStatus.FOUND, bracket: tuple[float, float] = (4, 8),
         threshold: float = 0.2, label: int | None = PERSON) -> Any:  # fmt: skip
    return bootstrap_search(
        clean=evidence(), points=points, threshold_kind=ThresholdKind.RELATIVE_DROP,
        threshold=threshold, class_label=label, status=status, bracket=bracket,
        samples=samples, seed=seed,
    )  # fmt: skip


POINTS = [
    BootstrapPoint(0, 0.0, None, None),  # synthetic
    point(1, 4.0, 0.1),
    point(2, 8.0, 0.3),
    point(3, 16.0, 0.6),
]


def test_same_seed_same_interval_and_zero_samples_is_null() -> None:
    first, again = _run(POINTS, seed=5), _run(POINTS, seed=5)
    assert first == again
    assert first.confidence_interval is not None
    assert _run(POINTS, seed=6).drop_ci != first.drop_ci
    empty = _run(POINTS, samples=0)
    assert empty.drop_ci == {} and empty.confidence_interval is None
    assert empty.near_threshold is False


def test_interval_contains_point_value_and_has_width() -> None:
    result = _run(POINTS)
    _, clean_class = average_precision_50(evidence(), np.ones(N, dtype=np.int64))
    for p in POINTS[1:]:
        assert p.attacked is not None
        _, attacked_class = average_precision_50(p.attacked, np.ones(N, dtype=np.int64))
        before, after = clean_class[PERSON], attacked_class[PERSON]
        assert before is not None and after is not None
        value = (before - after) / before
        low, high = result.drop_ci[p.order]
        assert low <= value <= high, (p.level, value, low, high)
        assert high - low > 0
    # Trên dữ liệu đầy đủ, mức sụt 0.1 ở level 4 và 0.3 ở level 8: giao ngưỡng 0.2 tại 6.
    assert result.confidence_interval is not None
    low, high = result.confidence_interval
    assert low <= 6.0 <= high
    assert high - low > 0


def test_near_threshold() -> None:
    # d(8) chỉ vượt ngưỡng 0.2 một chút (0.225): KTC của d(b) có cận dưới < ngưỡng.
    near = _run([point(1, 4.0, 0.05), point(2, 8.0, 0.225)], bracket=(4, 8))
    assert near.near_threshold is True
    # Vượt xa: d(a) = 0, d(b) = 0.8.
    far = _run([point(1, 4.0, 0.0), point(2, 8.0, 0.8)], bracket=(4, 8))
    assert far.near_threshold is False


@pytest.mark.db
def test_bootstrap_does_not_call_model(bootstrap_model_calls: tuple[int, int]) -> None:
    """Worker thật kết thúc một lần tìm ngưỡng có bootstrap: model chạy khi đánh giá các điểm,
    không chạy lần nào trong lúc bootstrap (fixture ở `conftest.py`)."""
    during_search, during_bootstrap = bootstrap_model_calls
    assert during_search > 0
    assert during_bootstrap == 0
