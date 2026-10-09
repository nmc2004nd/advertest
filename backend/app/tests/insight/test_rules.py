"""Luật điểm yếu, dải và câu kết luận (Phase R2 plan task 9): bảng đầu vào → đầu ra."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from advertest_contracts.enums import ConclusionCode
from advertest_contracts.models import AttackSpecMetadata, RunMetrics, Weakness
from backend.app.insight.phrases import conclude, percent
from backend.app.insight.rules import (
    GridRun,
    InsightAttack,
    band_of,
    grid_weakness,
    matrix_row,
    rank,
    search_weakness,
)

SPEC = UUID("00000000-0000-0000-0000-000000000001")


def _metrics(
    drop: float | None, per_class: dict[str, tuple[float, float | None]] | None = None
) -> Any:
    clean = 0.8 if drop is not None else 0.0
    attacked = clean * (1 - drop) if drop is not None else 0.0
    body: dict[str, Any] = {
        "clean": {"map50": clean, "map50_95": clean / 2},
        "attacked": {"map50": attacked, "map50_95": attacked / 2},
        "relative_drop": drop,
        "absolute_drop": clean - attacked,
        "attack_success_rate": None,
    }
    if per_class is not None:
        body["per_class"] = {
            k: {"clean_ap50": c, "attacked_ap50": a} for k, (c, a) in per_class.items()
        }
    return RunMetrics.model_validate(body)


def _attack(metadata: AttackSpecMetadata | None = None) -> InsightAttack:
    return InsightAttack(attack_spec_id=SPEC, name="fgsm", max_level=16.0, metadata=metadata)


def _runs(*pairs: tuple[float, float | None]) -> list[GridRun]:
    return [GridRun(level=level, metrics=_metrics(drop)) for level, drop in pairs]


@pytest.mark.parametrize(
    ("ratio", "band"),
    [(0.0, 0), (0.1, 0), (0.25, 0), (0.2500001, 1), (0.5, 1), (0.75, 2), (0.9, 3), (1.0, 3)],
)
def test_band_is_left_open_right_closed(ratio: float, band: int) -> None:
    assert band_of(ratio) == band


@pytest.mark.parametrize(
    ("runs", "level", "drop"),
    [
        # Level nhỏ nhất đạt 0.3, dù level lớn hơn sụt nhiều hơn; thứ tự vào không quan trọng.
        ([(8.0, 0.9), (2.0, 0.34), (1.0, 0.1)], 2.0, 0.34),
        # Không level nào đạt 0.3: level sụt nhiều nhất.
        ([(1.0, 0.12), (2.0, 0.2), (4.0, 0.15)], 2.0, 0.2),
        # Đúng bằng ngưỡng là đạt.
        ([(1.0, 0.3), (2.0, 0.5)], 1.0, 0.3),
        # Run không có relative_drop (mAP sạch bằng 0) bị bỏ qua.
        ([(1.0, None), (2.0, 0.4)], 2.0, 0.4),
    ],
)
def test_grid_weakness_level(
    runs: list[tuple[float, float | None]], level: float, drop: float
) -> None:
    weakness = grid_weakness(_attack(), _runs(*runs))
    assert weakness is not None
    assert (weakness.level, weakness.relative_drop) == (level, drop)
    assert weakness.level_ratio == level / 16.0
    assert weakness.kind == "grid" and weakness.breaking_point is None


@pytest.mark.parametrize("runs", [[], [(1.0, None)], [(1.0, 0.05), (2.0, 0.0999)]])
def test_grid_weakness_hidden_below_visible_drop(runs: list[tuple[float, float | None]]) -> None:
    assert grid_weakness(_attack(), _runs(*runs)) is None


def test_grid_weakness_worst_class_and_label() -> None:
    metrics = _metrics(
        0.4,
        {"car": (0.8, 0.4), "person": (0.5, 0.1), "bus": (0.0, 0.0), "van": (0.6, None)},
    )
    metadata = AttackSpecMetadata(
        display_name="FGSM", description="Nhiễu", realism="low", level_labels={"4.0": "mạnh"}
    )
    weakness = grid_weakness(_attack(metadata), [GridRun(level=4.0, metrics=metrics)])
    assert weakness is not None
    assert weakness.class_name == "person"
    assert weakness.class_relative_drop == pytest.approx(0.8)
    assert weakness.level_label == "mạnh"


def test_grid_weakness_class_tie_takes_smaller_name() -> None:
    metrics = _metrics(0.4, {"van": (0.5, 0.25), "car": (0.8, 0.4)})
    weakness = grid_weakness(_attack(), [GridRun(level=4.0, metrics=metrics)])
    assert weakness is not None and weakness.class_name == "car"


def _w(ratio: float, drop: float | None, name: str = "a") -> Weakness:
    if drop is None:
        return search_weakness(
            InsightAttack(attack_spec_id=uuid4(), name=name, max_level=1.0), ratio
        )
    return Weakness(
        attack_spec_id=uuid4(),
        attack_name=name,
        kind="grid",
        level=ratio,
        level_ratio=ratio,
        level_label=None,
        relative_drop=drop,
        breaking_point=None,
        class_name=None,
        class_relative_drop=None,
    )


def test_rank_orders_by_ratio_then_drop_and_keeps_five() -> None:
    items = [
        _w(0.5, 0.4, "c"),
        _w(0.25, 0.3, "b"),
        _w(0.25, None, "s"),
        _w(0.25, 0.6, "a"),
        _w(0.75, 0.9, "d"),
        _w(1.0, 0.95, "e"),
        _w(0.1, 0.15, "z"),
    ]
    assert [w.attack_name for w in rank(items)] == ["z", "a", "b", "s", "c"]


def test_matrix_row_bands_and_empty_cells() -> None:
    row = matrix_row(_attack(), _runs((1.0, 0.1), (4.0, 0.2), (3.0, 0.35), (16.0, None)))
    assert row is not None
    cells = [(c.band, c.max_relative_drop, c.runs) for c in row.cells]
    assert cells == [(0, 0.35, 3), (1, None, 0), (2, None, 0), (3, None, 0)]
    assert matrix_row(_attack(), _runs((1.0, None))) is None


# ---------------------------------------------------------------- câu kết luận


def _grid(**changes: Any) -> Weakness:
    base: dict[str, Any] = {
        "attack_spec_id": str(SPEC),
        "attack_name": "fog",
        "kind": "grid",
        "level": 3.0,
        "level_ratio": 0.6,
        "level_label": None,
        "relative_drop": 0.42,
        "breaking_point": None,
        "class_name": "car",
        "class_relative_drop": 0.5,
    }
    base.update(changes)
    return Weakness.model_validate(base)


@pytest.mark.parametrize(
    ("weaknesses", "has_data", "code", "fragments"),
    [
        ([], False, ConclusionCode.NO_DATA, ["Chưa có run"]),
        ([], True, ConclusionCode.ROBUST, ["10%"]),
        ([_grid()], True, ConclusionCode.WEAK, ["fog", "mức 3", "42%"]),
        ([_grid(level_label="sương dày")], True, ConclusionCode.WEAK, ["mức 3 (sương dày)"]),
        ([_grid(class_relative_drop=0.84)], True, ConclusionCode.WEAK_CLASS, ["car", "84%"]),
        ([_grid(relative_drop=0.1, class_relative_drop=0.2)], True, ConclusionCode.WEAK_CLASS, []),
        ([_grid(class_relative_drop=0.83)], True, ConclusionCode.WEAK, []),
        ([_grid(class_name=None, class_relative_drop=None)], True, ConclusionCode.WEAK, []),
        (
            [
                _grid(
                    kind="search",
                    level=2.5,
                    relative_drop=None,
                    breaking_point=2.5,
                    class_name=None,
                    class_relative_drop=None,
                )
            ],
            True,
            ConclusionCode.WEAK,
            ["fog", "gãy", "2.5"],
        ),
        # weak_class chỉ xét điểm yếu đầu tiên.
        (
            [_grid(), _grid(attack_name="snow", class_relative_drop=0.9)],
            True,
            ConclusionCode.WEAK,
            ["fog", "1 điểm yếu khác"],
        ),
    ],
)
def test_conclusion_table(
    weaknesses: list[Weakness], has_data: bool, code: ConclusionCode, fragments: list[str]
) -> None:
    conclusion = conclude(weaknesses, has_data=has_data)
    assert conclusion.code == code
    for fragment in fragments:
        assert fragment in conclusion.text
    assert conclude(list(weaknesses), has_data=has_data) == conclusion


@pytest.mark.parametrize(("value", "text"), [(0.42, "42%"), (0.005, "1%"), (0.994, "99%")])
def test_percent_rounds_half_up(value: float, text: str) -> None:
    assert percent(value) == text
