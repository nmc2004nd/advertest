"""Đánh giá tiêu chí tự động, chỉ mang tính tham khảo (requirements.md Phase 8, Đánh giá tiêu chí;
plan task 15). Hàm thuần: không đọc DB, dữ liệu do `views.py` nạp.

`max_drop_at_level` (attack quét lưới, chỉ run toàn slice):
- run `completed` (hoặc `skipped` do `cached`, có metric chép từ run gốc) không `partial`: đại
  lượng ≤ ngưỡng → `pass`, > ngưỡng → `fail`;
- level `skipped` do `early_stop`: dùng đại lượng của run kích hoạt (kickoff), `detail` ghi rõ;
- còn lại (không có run, run `partial`, `failed`, `cancelled`, đại lượng không xác định) →
  `inconclusive`.

`min_breaking_point` (kết quả tìm ngưỡng cuối, `bracket = (a, b]`, điểm gãy = b):
- `not_reached` → `pass`; `below_min` → `fail`; `stopped_limit`, `failed`, chưa có kết quả cuối →
  `inconclusive`;
- `found`, `non_monotonic`: `near_threshold` hoặc khoảng tin cậy chứa level → `inconclusive`;
  a ≥ level → `pass`; b < level → `fail`; còn lại (level trong khoảng) → `inconclusive`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from uuid import UUID

from advertest_contracts.enums import (
    CriterionKind,
    CriterionStatus,
    RunStatus,
    SearchStage,
    SearchStatus,
)
from advertest_contracts.models import (
    CriterionResult,
    PassCriterion,
    ProtocolBody,
    RunMetrics,
    SearchResult,
)
from ml_core.metrics.threshold import threshold_quantity

S = CriterionStatus


@dataclass(frozen=True)
class RunPoint:
    """Một run toàn slice của attack quét lưới."""

    run_id: UUID
    level: float
    status: RunStatus
    reason_code: str | None
    trigger_run_id: UUID | None
    metrics: RunMetrics | None


def _usable(point: RunPoint) -> bool:
    cached = point.status == RunStatus.SKIPPED and point.reason_code == "cached"
    return (
        (point.status == RunStatus.COMPLETED or cached)
        and point.metrics is not None
        and not point.metrics.partial
    )


def _quantity(point: RunPoint, criterion: PassCriterion) -> float | None:
    assert point.metrics is not None
    try:
        return threshold_quantity(point.metrics, criterion.threshold_kind, criterion.class_filter)
    except ValueError:  # class_filter không có trong per_class của metric
        return None


def _result(
    index: int, status: CriterionStatus, value: float | None, detail: str
) -> CriterionResult:
    return CriterionResult(index=index, status=status, value=value, detail=detail)


def _compare(
    index: int, criterion: PassCriterion, value: float | None, where: str
) -> CriterionResult:
    name = criterion.threshold_kind.value
    if value is None:
        return _result(index, S.INCONCLUSIVE, None, f"{name} không xác định được {where}")
    ok = value <= criterion.threshold
    sign = "≤" if ok else ">"
    return _result(
        index,
        S.PASS if ok else S.FAIL,
        value,
        f"{name} {where} là {value:.4g} {sign} {criterion.threshold:g}",
    )


def max_drop_at_level(
    index: int,
    criterion: PassCriterion,
    points: Sequence[RunPoint],
    by_id: Mapping[UUID, RunPoint],
) -> CriterionResult:
    level = f"tại level {criterion.level:g}"
    at_level = [p for p in points if p.level == criterion.level]
    if not at_level:
        return _result(index, S.INCONCLUSIVE, None, f"Không có run toàn slice {level}")
    point = at_level[0]
    if point.status == RunStatus.SKIPPED and point.reason_code == "early_stop":
        trigger = by_id.get(point.trigger_run_id) if point.trigger_run_id else None
        if trigger is None or not _usable(trigger):
            return _result(
                index,
                S.INCONCLUSIVE,
                None,
                f"Level bị dừng sớm nhưng không có run kích hoạt {level}",
            )
        return _compare(
            index,
            criterion,
            _quantity(trigger, criterion),
            f"{level} (suy từ dừng sớm tại level {trigger.level:g})",
        )
    if not _usable(point):
        partial = point.metrics is not None and point.metrics.partial
        why = "metric chỉ tính trên một phần ảnh (partial)" if partial else f"run {point.status}"
        return _result(index, S.INCONCLUSIVE, None, f"Không có run completed {level}: {why}")
    return _compare(index, criterion, _quantity(point, criterion), level)


def min_breaking_point(
    index: int, criterion: PassCriterion, result: SearchResult | None
) -> CriterionResult:
    level = criterion.level
    if result is None or result.stage != SearchStage.DONE or result.status is None:
        return _result(index, S.INCONCLUSIVE, None, "Chưa có kết quả tìm ngưỡng cuối")
    status = result.status
    if status == SearchStatus.NOT_REACHED:
        return _result(
            index, S.PASS, None, f"Không chạm ngưỡng trong dải (> {result.bracket[1]:g})"
        )
    if status == SearchStatus.BELOW_MIN:
        return _result(index, S.FAIL, None, "Đã vượt ngưỡng ngay ở cận dưới của dải")
    if status in (SearchStatus.STOPPED_LIMIT, SearchStatus.FAILED):
        return _result(index, S.INCONCLUSIVE, None, f"Tìm ngưỡng kết thúc với {status}")
    a, b = result.bracket
    bracket = f"điểm gãy trong ({a:g}, {b:g}]"
    if result.near_threshold:
        return _result(index, S.INCONCLUSIVE, b, f"{bracket}, sát ngưỡng (near_threshold)")
    ci = result.confidence_interval
    if ci is not None and ci[0] <= level <= ci[1]:
        return _result(
            index,
            S.INCONCLUSIVE,
            b,
            f"{bracket}; khoảng tin cậy [{ci[0]:g}, {ci[1]:g}] chứa level {level:g}",
        )
    if a >= level:
        return _result(index, S.PASS, b, f"{bracket}, cận dưới {a:g} ≥ {level:g}")
    if b < level:
        return _result(index, S.FAIL, b, f"{bracket}, điểm gãy {b:g} < {level:g}")
    return _result(index, S.INCONCLUSIVE, b, f"{bracket} chứa level {level:g}")


def evaluate(
    body: ProtocolBody,
    grid: Mapping[str, Sequence[RunPoint]],
    by_id: Mapping[UUID, RunPoint],
    searches: Mapping[str, SearchResult],
) -> list[CriterionResult]:
    """Kết quả theo thứ tự `body.pass_criteria`; khóa của `grid`, `searches` là tên attack."""
    out: list[CriterionResult] = []
    for index, criterion in enumerate(body.pass_criteria):
        name = criterion.attack_spec_name
        if criterion.kind == CriterionKind.MAX_DROP_AT_LEVEL:
            out.append(max_drop_at_level(index, criterion, grid.get(name, ()), by_id))
        else:
            out.append(min_breaking_point(index, criterion, searches.get(name)))
    return out
