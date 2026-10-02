"""Đánh giá tiêu chí (Phase 8 task 15; validation.md mục Tiêu chí), không cần DB."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from advertest_contracts.enums import CriterionStatus, RunStatus
from advertest_contracts.models import PassCriterion, RunMetrics, SearchResult
from backend.app.reviews.criteria import RunPoint, max_drop_at_level, min_breaking_point

S = CriterionStatus


def _metrics(drop: float, *, partial: bool = False, person: float | None = None) -> RunMetrics:
    clean = 0.5
    per_class: dict[str, Any] | None = None
    if person is not None:
        per_class = {"person": {"clean_ap50": 0.4, "attacked_ap50": 0.4 * (1 - person)}}
    return RunMetrics.model_validate(
        {
            "clean": {"map50": clean, "map50_95": 0.3},
            "attacked": {"map50": clean * (1 - drop), "map50_95": 0.2},
            "relative_drop": drop,
            "absolute_drop": clean * drop,
            "attack_success_rate": 0.5,
            "per_class": per_class,
            "partial": partial,
        }
    )


def _point(level: float, status: RunStatus = RunStatus.COMPLETED, **kw: Any) -> RunPoint:
    return RunPoint(
        run_id=kw.pop("run_id", uuid.uuid4()),
        level=level,
        status=status,
        reason_code=kw.pop("reason_code", None),
        trigger_run_id=kw.pop("trigger_run_id", None),
        metrics=kw.pop("metrics", None),
    )


def _grid(level: float = 4, threshold: float = 0.3, **kw: Any) -> PassCriterion:
    return PassCriterion.model_validate(
        {
            "kind": "max_drop_at_level",
            "attack_spec_name": "fgsm",
            "level": level,
            "threshold_kind": "relative_drop",
            "threshold": threshold,
            **kw,
        }
    )


@pytest.mark.parametrize(
    ("drop", "threshold", "status"),
    [(0.2, 0.3, S.PASS), (0.5, 0.5, S.PASS), (0.31, 0.3, S.FAIL)],  # bằng ngưỡng → pass
)
def test_max_drop_pass_fail(drop: float, threshold: float, status: CriterionStatus) -> None:
    point = _point(4, metrics=_metrics(drop))
    result = max_drop_at_level(0, _grid(threshold=threshold), [point], {point.run_id: point})
    assert result.status == status and result.value == pytest.approx(drop)


@pytest.mark.parametrize(
    "point",
    [
        _point(4, RunStatus.STOPPED_LIMIT, reason_code="time", metrics=_metrics(0.1, partial=True)),
        _point(4, RunStatus.FAILED, reason_code="error"),
        _point(4, RunStatus.CANCELLED, reason_code="cancelled"),
        _point(8, metrics=_metrics(0.1)),  # level khác
    ],
)
def test_max_drop_inconclusive(point: RunPoint) -> None:
    result = max_drop_at_level(0, _grid(), [point], {point.run_id: point})
    assert result.status == S.INCONCLUSIVE and result.value is None


def test_max_drop_cached_run_counts() -> None:
    point = _point(4, RunStatus.SKIPPED, reason_code="cached", metrics=_metrics(0.1))
    assert max_drop_at_level(0, _grid(), [point], {point.run_id: point}).status == S.PASS


def test_max_drop_early_stop_uses_trigger_run() -> None:
    """Kickoff Phase 8: level bị dừng sớm dùng đại lượng của run kích hoạt."""
    trigger = _point(2, metrics=_metrics(0.97))
    skipped = _point(4, RunStatus.SKIPPED, reason_code="early_stop", trigger_run_id=trigger.run_id)
    by_id = {p.run_id: p for p in (trigger, skipped)}
    result = max_drop_at_level(0, _grid(), [trigger, skipped], by_id)
    assert result.status == S.FAIL and result.value == pytest.approx(0.97)
    assert "dừng sớm tại level 2" in result.detail


def test_class_filter_applied() -> None:
    point = _point(4, metrics=_metrics(0.9, person=0.1))
    criterion = _grid(class_filter="person")
    result = max_drop_at_level(0, criterion, [point], {point.run_id: point})
    assert result.status == S.PASS and result.value == pytest.approx(0.1)
    missing = max_drop_at_level(0, _grid(class_filter="bicycle"), [point], {point.run_id: point})
    assert missing.status == S.INCONCLUSIVE


def _search(status: str | None, bracket: tuple[float, float], **kw: Any) -> SearchResult:
    has_bp = status in ("found", "non_monotonic")
    return SearchResult.model_validate(
        {
            "experiment_id": str(uuid.uuid4()),
            "attack_spec_id": str(uuid.uuid4()),
            "stage": "done" if status else "bisect_full",
            "status": status,
            "threshold_kind": "relative_drop",
            "threshold": 0.2,
            "class_filter": None,
            "metric_kind": "map50",
            "breaking_point": bracket[1] if has_bp else None,
            "bracket": list(bracket),
            "near_threshold": kw.pop("near", False),
            "confidence_interval": kw.pop("ci", None),
            "max_points": 20,
            "points_used": 0,
            "message": "lỗi" if status == "failed" else None,
            "trajectory": [],
        }
    )


BP = PassCriterion.model_validate(
    {
        "kind": "min_breaking_point",
        "attack_spec_name": "pgd_linf",
        "level": 2,
        "threshold_kind": "relative_drop",
        "threshold": 0.2,
    }
)


@pytest.mark.parametrize(
    ("result", "status"),
    [
        (_search("found", (2, 3)), S.PASS),  # cận dưới ≥ level
        (_search("non_monotonic", (3, 4)), S.PASS),
        (_search("not_reached", (31, 32)), S.PASS),
        (_search("found", (1, 1.5)), S.FAIL),  # điểm gãy < level
        (_search("below_min", (0, 0.1)), S.FAIL),
        (_search("found", (1.5, 2.5)), S.INCONCLUSIVE),  # level trong bracket
        (_search("found", (2, 3), near=True), S.INCONCLUSIVE),
        (_search("found", (2.5, 3), ci=(1.5, 3)), S.INCONCLUSIVE),  # KTC chứa level
        (_search("stopped_limit", (0, 32)), S.INCONCLUSIVE),
        (_search("failed", (0, 32)), S.INCONCLUSIVE),
        (_search(None, (0, 32)), S.INCONCLUSIVE),  # chưa có kết quả cuối
        (None, S.INCONCLUSIVE),
    ],
)
def test_min_breaking_point(result: SearchResult | None, status: CriterionStatus) -> None:
    assert min_breaking_point(0, BP, result).status == status
