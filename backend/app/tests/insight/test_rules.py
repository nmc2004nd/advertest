"""Luật điểm yếu, dải và câu kết luận (Phase R2 plan task 9): bảng đầu vào → đầu ra."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from advertest_contracts.enums import ConclusionCode, RunStatus, SkipReason, StopReason
from advertest_contracts.models import AttackSpecMetadata, RunMetrics, StatusReason, Weakness
from backend.app.insight.phrases import conclude, percent
from backend.app.insight.rules import (
    GridRun,
    InsightAttack,
    InsightRun,
    band_of,
    grid_runs,
    grid_weakness,
    has_data,
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


# ---------------------------------------------------------------- run được tính (Chốt ở Group 1)


def _run(
    level: float,
    status: RunStatus,
    drop: float | None = None,
    reason: StatusReason | None = None,
    scope: str = "full",
) -> InsightRun:
    return InsightRun(
        run_id=uuid4(),
        attack_spec_id=SPEC,
        scope=scope,
        level=level,
        status=status,
        status_reason=reason,
        metrics=_metrics(drop) if drop is not None else None,
    )


def _cached(level: float, drop: float) -> InsightRun:
    reason = StatusReason(code=SkipReason.CACHED, message="Fingerprint trùng run gốc")
    return _run(level, RunStatus.SKIPPED, drop, reason)


def _early_stop(level: float, trigger: InsightRun) -> InsightRun:
    reason = StatusReason(
        code=SkipReason.EARLY_STOP, message="Model đã sụp", trigger_run_id=trigger.run_id
    )
    return _run(level, RunStatus.SKIPPED, reason=reason)


def _levels(runs: list[InsightRun]) -> list[tuple[float, float | None]]:
    return sorted((r.level, r.metrics.relative_drop) for r in grid_runs(runs)[SPEC])


def test_cached_runs_count_like_completed() -> None:
    completed = [_run(1.0, RunStatus.COMPLETED, 0.1), _run(4.0, RunStatus.COMPLETED, 0.6)]
    cached = [_cached(1.0, 0.1), _cached(4.0, 0.6)]
    assert has_data(cached)
    assert _levels(cached) == _levels(completed) == [(1.0, 0.1), (4.0, 0.6)]
    attack = _attack()
    assert grid_weakness(attack, grid_runs(cached)[SPEC]) == grid_weakness(
        attack, grid_runs(completed)[SPEC]
    )
    assert matrix_row(attack, grid_runs(cached)[SPEC]) == matrix_row(
        attack, grid_runs(completed)[SPEC]
    )
    assert conclude([], has_data=has_data(cached)).code == ConclusionCode.ROBUST


def test_other_runs_do_not_count() -> None:
    error = StatusReason(code="error", message="Lỗi")
    limit = StatusReason(code=StopReason.TIME, message="Hết giờ")
    runs = [
        _run(1.0, RunStatus.FAILED, reason=error),
        _run(2.0, RunStatus.QUEUED),
        _run(4.0, RunStatus.COMPLETED),  # chưa có metric
        _run(8.0, RunStatus.SKIPPED, 0.5, StatusReason(code=SkipReason.INCOMPATIBLE, message="x")),
        _run(16.0, RunStatus.COMPLETED, 0.9, scope="subset"),  # tìm ngưỡng, không thuộc lưới
    ]
    assert grid_runs(runs) == {}
    assert has_data(runs[:4]) is False
    partial = _run(2.0, RunStatus.STOPPED_LIMIT, 0.2, limit)
    assert _levels([*runs, partial]) == [(2.0, 0.2)]


def test_early_stopped_levels_take_trigger_drop() -> None:
    # max 16: 2 và 4 ở (0, .25], 8 ở (.25, .5], 16 ở (.75, 1]; (.5, .75] không có level nào.
    trigger = _run(4.0, RunStatus.COMPLETED, 0.98)
    runs = [_run(2.0, RunStatus.COMPLETED, 0.1), trigger]
    runs += [_early_stop(8.0, trigger), _early_stop(16.0, trigger)]
    assert _levels(runs) == [(2.0, 0.1), (4.0, 0.98), (8.0, 0.98), (16.0, 0.98)]
    row = matrix_row(_attack(), grid_runs(runs)[SPEC])
    assert row is not None
    assert [c.max_relative_drop for c in row.cells] == [0.98, 0.98, None, 0.98]
    assert [c.runs for c in row.cells] == [2, 1, 0, 1]
    weakness = grid_weakness(_attack(), grid_runs(runs)[SPEC])
    assert weakness is not None and weakness.level == 4.0  # run kích hoạt, không phải level sau


def test_early_stop_triggered_by_cached_run() -> None:
    trigger = _cached(2.0, 0.97)
    runs = [trigger, _early_stop(4.0, trigger), _early_stop(8.0, trigger)]
    weakness = grid_weakness(_attack(), grid_runs(runs)[SPEC])
    assert weakness is not None
    assert (weakness.level, weakness.relative_drop) == (2.0, 0.97)
    assert _levels(runs) == [(2.0, 0.97), (4.0, 0.97), (8.0, 0.97)]


def test_early_stop_without_measured_trigger_is_ignored() -> None:
    trigger = _run(2.0, RunStatus.FAILED, reason=StatusReason(code="error", message="Lỗi"))
    assert grid_runs([trigger, _early_stop(4.0, trigger)]) == {}
