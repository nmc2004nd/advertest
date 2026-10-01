"""Đại lượng so với ngưỡng của tự tìm ngưỡng (requirements.md Phase 7, mục "Đại lượng dùng để so
với ngưỡng"; plan task 10).

| `threshold_kind`      | không `class_filter`        | có `class_filter`              |
|-----------------------|-----------------------------|--------------------------------|
| `relative_drop`       | mức sụt tương đối mAP@0.5   | mức sụt tương đối AP@0.5 class |
| `absolute_drop`       | mức sụt tuyệt đối mAP@0.5   | mức sụt tuyệt đối AP@0.5 class |
| `attack_success_rate` | ASR mọi object              | ASR object của class           |

`None` khi không tính được (mAP/AP sạch bằng 0 với ngưỡng tương đối, class không có ground truth,
không còn object nào được detect đúng trên ảnh sạch): thuật toán kết thúc `failed`.
"""

from __future__ import annotations

from advertest_contracts.enums import ThresholdKind
from advertest_contracts.models import RunMetrics


def relative(clean: float | None, attacked: float | None) -> float | None:
    if clean is None or attacked is None or clean == 0:
        return None
    return (clean - attacked) / clean


def absolute(clean: float | None, attacked: float | None) -> float | None:
    if clean is None or attacked is None:
        return None
    return clean - attacked


def threshold_quantity(
    metrics: RunMetrics, threshold_kind: ThresholdKind, class_filter: str | None = None
) -> float | None:
    """Đại lượng so với ngưỡng của một run, từ `RunResult.metrics` (gồm metric sạch)."""
    if class_filter is None:
        if threshold_kind == ThresholdKind.RELATIVE_DROP:
            return relative(metrics.clean.map50, metrics.attacked.map50)
        if threshold_kind == ThresholdKind.ABSOLUTE_DROP:
            return absolute(metrics.clean.map50, metrics.attacked.map50)
        return metrics.attack_success_rate
    per_class = metrics.per_class or {}
    if class_filter not in per_class:
        raise ValueError(f"class {class_filter!r} không có trong per_class của metric")
    cls = per_class[class_filter]
    if threshold_kind == ThresholdKind.RELATIVE_DROP:
        return relative(cls.clean_ap50, cls.attacked_ap50)
    if threshold_kind == ThresholdKind.ABSOLUTE_DROP:
        return absolute(cls.clean_ap50, cls.attacked_ap50)
    return cls.attack_success_rate
