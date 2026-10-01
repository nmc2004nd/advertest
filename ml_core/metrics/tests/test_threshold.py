"""Đại lượng so với ngưỡng (validation.md Phase 7, mục "Đại lượng ngưỡng và bootstrap")."""

import pytest

from advertest_contracts.enums import ThresholdKind
from advertest_contracts.models import ClassRunMetrics, MapPair, RunMetrics
from ml_core.metrics.threshold import threshold_quantity

REL, ABS, ASR = (
    ThresholdKind.RELATIVE_DROP,
    ThresholdKind.ABSOLUTE_DROP,
    ThresholdKind.ATTACK_SUCCESS_RATE,
)


def _metrics(clean: float = 0.5, attacked: float = 0.3) -> RunMetrics:
    return RunMetrics(
        clean=MapPair(map50=clean, map50_95=clean / 2),
        attacked=MapPair(map50=attacked, map50_95=attacked / 2),
        relative_drop=None if clean == 0 else (clean - attacked) / clean,
        absolute_drop=clean - attacked,
        attack_success_rate=0.4,
        per_class={
            "car": ClassRunMetrics(clean_ap50=0.8, attacked_ap50=0.6, attack_success_rate=0.25),
            "person": ClassRunMetrics(clean_ap50=0.4, attacked_ap50=0.1, attack_success_rate=0.7),
            "truck": ClassRunMetrics(clean_ap50=None, attacked_ap50=None),
            "bus": ClassRunMetrics(clean_ap50=0.0, attacked_ap50=0.0, attack_success_rate=None),
        },
    )


@pytest.mark.parametrize(
    ("kind", "class_filter", "expected"),
    [
        (REL, None, 0.4),
        (ABS, None, 0.2),
        (ASR, None, 0.4),
        (REL, "car", 0.25),
        (ABS, "car", 0.2),
        (ASR, "car", 0.25),
        (REL, "person", 0.75),
        (ABS, "person", 0.3),
        (ASR, "person", 0.7),
    ],
)
def test_quantity(kind: ThresholdKind, class_filter: str | None, expected: float) -> None:
    assert threshold_quantity(_metrics(), kind, class_filter) == pytest.approx(expected)


def test_zero_clean_map_with_relative_threshold_is_none() -> None:
    zero = _metrics(clean=0.0, attacked=0.0)
    assert threshold_quantity(zero, REL) is None
    assert threshold_quantity(zero, ABS) == 0.0


@pytest.mark.parametrize(
    ("kind", "class_filter"),
    [(REL, "truck"), (ABS, "truck"), (ASR, "truck"), (REL, "bus"), (ASR, "bus")],
)
def test_class_without_data_is_none(kind: ThresholdKind, class_filter: str) -> None:
    assert threshold_quantity(_metrics(), kind, class_filter) is None


def test_no_correct_objects_for_asr_is_none() -> None:
    metrics = _metrics().model_copy(update={"attack_success_rate": None})
    assert threshold_quantity(metrics, ASR) is None


def test_unknown_class_is_rejected() -> None:
    with pytest.raises(ValueError):
        threshold_quantity(_metrics(), REL, "bicycle")
