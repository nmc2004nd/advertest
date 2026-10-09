"""Luật điểm yếu và ma trận độ bền (requirements.md Phase R2, Behaviour Insight), hàm thuần.

- Điểm yếu quét lưới: level nhỏ nhất có `relative_drop ≥ WEAKNESS_DROP`; không có thì level có
  `relative_drop` lớn nhất. Kèm class có mức sụt AP50 tương đối lớn nhất tại level đó.
- Run `skipped` vì `early_stop` không cần xét riêng: run kích hoạt luôn có mức sụt ≥ 0.95 ở level
  nhỏ hơn, nên đã là điểm yếu được chọn.
- Điểm yếu tìm ngưỡng: điểm gãy `found`.
- Chỉ giữ điểm có `relative_drop ≥ WEAKNESS_VISIBLE_DROP` hoặc có điểm gãy; `level_ratio` nhỏ
  trước, bằng nhau thì `relative_drop` lớn trước; tối đa `MAX_WEAKNESSES`.
- Ma trận: mỗi attack quét lưới có run đo được một hàng, 4 dải `level_ratio`, ô là
  `relative_drop` lớn nhất của các run thuộc dải.
- `level_ratio = level / primary_param.max`, như ranking Phase 6.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from advertest_contracts.models import (
    MAX_WEAKNESSES,
    ROBUSTNESS_BANDS,
    WEAKNESS_DROP,
    WEAKNESS_VISIBLE_DROP,
    AttackSpecMetadata,
    RobustnessCell,
    RobustnessRow,
    RunMetrics,
    Weakness,
)


@dataclass(frozen=True)
class GridRun:
    level: float
    metrics: RunMetrics


@dataclass(frozen=True)
class InsightAttack:
    attack_spec_id: UUID
    name: str
    max_level: float  # primary_param.max của spec
    metadata: AttackSpecMetadata | None = None


def level_ratio(level: float, max_level: float) -> float:
    if max_level <= 0:
        raise ValueError("primary_param.max phải dương")
    return min(1.0, max(0.0, level / max_level))


def band_of(ratio: float) -> int:
    """Chỉ số dải `(lo, hi]` chứa `ratio`; ratio 0 thuộc dải đầu."""
    for i, (_, hi) in enumerate(ROBUSTNESS_BANDS):
        if ratio <= hi:
            return i
    return len(ROBUSTNESS_BANDS) - 1


def _label(attack: InsightAttack, level: float) -> str | None:
    return attack.metadata.label_for(level) if attack.metadata is not None else None


def _measured(runs: Sequence[GridRun]) -> list[tuple[float, float, RunMetrics]]:
    """(level, relative_drop, metrics) của run có `relative_drop`, theo level tăng dần."""
    rows = [
        (run.level, run.metrics.relative_drop, run.metrics)
        for run in runs
        if run.metrics.relative_drop is not None
    ]
    return sorted(rows, key=lambda row: row[0])


def worst_class(metrics: RunMetrics) -> tuple[str, float] | None:
    """Class có mức sụt AP50 tương đối lớn nhất (bằng nhau lấy tên nhỏ hơn); None khi không
    class nào có AP50 sạch dương."""
    drops = [
        (name, (value.clean_ap50 - value.attacked_ap50) / value.clean_ap50)
        for name, value in (metrics.per_class or {}).items()
        if value.clean_ap50 and value.attacked_ap50 is not None
    ]
    if not drops:
        return None
    return min(drops, key=lambda item: (-item[1], item[0]))


def grid_weakness(attack: InsightAttack, runs: Sequence[GridRun]) -> Weakness | None:
    measured = _measured(runs)
    if not measured:
        return None
    hits = [row for row in measured if row[1] >= WEAKNESS_DROP]
    level, drop, metrics = hits[0] if hits else max(measured, key=lambda row: row[1])
    if drop < WEAKNESS_VISIBLE_DROP:
        return None
    worst = worst_class(metrics)
    return Weakness(
        attack_spec_id=attack.attack_spec_id,
        attack_name=attack.name,
        kind="grid",
        level=level,
        level_ratio=level_ratio(level, attack.max_level),
        level_label=_label(attack, level),
        relative_drop=drop,
        breaking_point=None,
        class_name=worst[0] if worst else None,
        class_relative_drop=worst[1] if worst else None,
    )


def search_weakness(attack: InsightAttack, breaking_point: float) -> Weakness:
    return Weakness(
        attack_spec_id=attack.attack_spec_id,
        attack_name=attack.name,
        kind="search",
        level=breaking_point,
        level_ratio=level_ratio(breaking_point, attack.max_level),
        level_label=_label(attack, breaking_point),
        relative_drop=None,
        breaking_point=breaking_point,
        class_name=None,
        class_relative_drop=None,
    )


def rank(weaknesses: Sequence[Weakness]) -> list[Weakness]:
    """Gãy sớm hơn đứng trước; bằng nhau thì sụt nhiều hơn trước (điểm gãy không có mức sụt nên
    đứng sau); bằng nhau nữa thì giữ thứ tự vào. Tối đa `MAX_WEAKNESSES`."""
    ordered = sorted(
        weaknesses,
        key=lambda w: (w.level_ratio, w.relative_drop is None, -(w.relative_drop or 0.0)),
    )
    return ordered[:MAX_WEAKNESSES]


def matrix_row(attack: InsightAttack, runs: Sequence[GridRun]) -> RobustnessRow | None:
    """None khi attack chưa có run đo được."""
    measured = _measured(runs)
    if not measured:
        return None
    worst: list[float | None] = [None] * len(ROBUSTNESS_BANDS)
    counts = [0] * len(ROBUSTNESS_BANDS)
    for level, drop, _ in measured:
        band = band_of(level_ratio(level, attack.max_level))
        current = worst[band]
        worst[band] = drop if current is None else max(current, drop)
        counts[band] += 1
    return RobustnessRow(
        attack_spec_id=attack.attack_spec_id,
        attack_name=attack.name,
        cells=[
            RobustnessCell(band=i, max_relative_drop=worst[i], runs=counts[i])
            for i in range(len(ROBUSTNESS_BANDS))
        ],
    )
