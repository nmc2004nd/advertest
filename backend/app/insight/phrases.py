"""Câu kết luận sinh theo luật (requirements.md Phase R2, Behaviour Insight).

Hàm thuần: cùng danh sách điểm yếu cho cùng câu. Report sau này dùng chung các câu ở đây.

- `no_data`: chưa run nào có metric.
- `robust`: có dữ liệu mà không có điểm yếu.
- `weak`: câu nêu attack, level (kèm nhãn từ metadata nếu có) và mức sụt của điểm yếu đầu tiên;
  điểm yếu tìm ngưỡng nêu điểm gãy thay cho mức sụt.
- `weak_class`: điểm yếu đầu tiên quét lưới và mức sụt của class ≥ 2 lần mức sụt toàn bộ.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from pydantic import JsonValue

from advertest_contracts.enums import ConclusionCode
from advertest_contracts.models import WEAKNESS_VISIBLE_DROP, Conclusion, Weakness

WEAK_CLASS_FACTOR = 2.0
# So sánh "gấp đôi trở lên" trên số thực: 2 · 0.42 có thể lệch 0.84 ở chữ số cuối.
_EPS = 1e-9


def percent(value: float) -> str:
    """0.42 → "42%" (làm tròn số nguyên, nửa lên)."""
    return f"{math.floor(value * 100 + 0.5)}%"


def _level(value: float, label: str | None) -> str:
    return f"mức {value:g} ({label})" if label else f"mức {value:g}"


def is_weak_class(weakness: Weakness) -> bool:
    if weakness.kind != "grid" or weakness.class_relative_drop is None:
        return False
    assert weakness.relative_drop is not None  # grid luôn có relative_drop (contract)
    return weakness.class_relative_drop >= WEAK_CLASS_FACTOR * weakness.relative_drop - _EPS


def _more(weaknesses: Sequence[Weakness]) -> str:
    others = len(weaknesses) - 1
    return f" Có thêm {others} điểm yếu khác." if others else ""


def conclude(weaknesses: Sequence[Weakness], *, has_data: bool) -> Conclusion:
    if not has_data:
        return Conclusion(
            code=ConclusionCode.NO_DATA,
            params={},
            text="Chưa có run nào có kết quả nên chưa kết luận được.",
        )
    if not weaknesses:
        return Conclusion(
            code=ConclusionCode.ROBUST,
            params={"visible_drop": WEAKNESS_VISIBLE_DROP},
            text=(
                "Chưa thấy điểm yếu: không attack nào làm mAP@0.5 sụt từ"
                f" {percent(WEAKNESS_VISIBLE_DROP)} trở lên ở các level đã chạy."
            ),
        )
    first = weaknesses[0]
    params: dict[str, JsonValue] = {
        "attack_name": first.attack_name,
        "kind": first.kind,
        "level": first.level,
        "level_label": first.level_label,
        "relative_drop": first.relative_drop,
        "breaking_point": first.breaking_point,
        "class_name": first.class_name,
        "class_relative_drop": first.class_relative_drop,
        "weaknesses": len(weaknesses),
    }
    if first.kind == "search":
        assert first.breaking_point is not None  # search luôn có điểm gãy (contract)
        text = (
            f"Điểm yếu chính: {first.attack_name} làm model gãy từ"
            f" {_level(first.breaking_point, first.level_label)}."
        )
        return Conclusion(code=ConclusionCode.WEAK, params=params, text=text + _more(weaknesses))
    assert first.relative_drop is not None
    text = (
        f"Điểm yếu chính: {first.attack_name} ở {_level(first.level, first.level_label)} làm"
        f" mAP@0.5 sụt {percent(first.relative_drop)}."
    )
    if is_weak_class(first):
        assert first.class_relative_drop is not None
        text += (
            f" Riêng class {first.class_name} sụt {percent(first.class_relative_drop)}, gấp"
            f" {first.class_relative_drop / first.relative_drop:.1f} lần toàn bộ."
        )
        code = ConclusionCode.WEAK_CLASS
    else:
        code = ConclusionCode.WEAK
    return Conclusion(code=code, params=params, text=text + _more(weaknesses))
