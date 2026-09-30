"""Thứ tự quét lưới và dừng sớm (validation.md Phase 6, mục Thứ tự và dừng sớm)."""

from uuid import UUID, uuid5

from advertest_contracts.enums import RunStatus
from advertest_contracts.models import MapPair, RunMetrics
from ml_core.runner.grid import GridRun, coarse_to_fine, collapsed, early_stop

NS = UUID("12345678-1234-5678-1234-567812345678")


def _id(level: float) -> UUID:
    return uuid5(NS, str(level))


def _metrics(attacked: float, clean: float = 0.5, partial: bool = False) -> RunMetrics:
    return RunMetrics(
        clean=MapPair(map50=clean, map50_95=clean / 2),
        attacked=MapPair(map50=attacked, map50_95=attacked / 2),
        relative_drop=None if clean == 0 else (clean - attacked) / clean,
        absolute_drop=clean - attacked,
        attack_success_rate=None,
        partial=partial,
    )


def _run(
    level: float, status: RunStatus = RunStatus.QUEUED, attacked: float | None = None
) -> GridRun:
    metrics = None if attacked is None else _metrics(attacked)
    return GridRun(_id(level), level, status, metrics)


def test_coarse_to_fine_order() -> None:
    assert coarse_to_fine([2, 4, 8, 16, 32]) == [2, 8, 32, 4, 16]
    assert coarse_to_fine([32, 2, 16, 4, 8]) == [2, 8, 32, 4, 16]
    assert coarse_to_fine([1, 2, 3, 4]) == [1, 3, 2, 4]
    assert coarse_to_fine([0.5]) == [0.5]
    assert coarse_to_fine([]) == []


def test_first_pass_covers_both_ends() -> None:
    order = coarse_to_fine([1, 2, 3, 4, 5])
    first_pass = order[:3]
    assert min(first_pass) == 1 and max(first_pass) == 5


def test_collapse_threshold() -> None:
    assert collapsed(_metrics(0.025))  # đúng 5%
    assert not collapsed(_metrics(0.026))
    assert not collapsed(_metrics(0.0, clean=0.0))  # mAP sạch = 0: không coi là sụp


def test_skips_only_larger_queued_levels() -> None:
    runs = [
        _run(2, RunStatus.COMPLETED, attacked=0.3),
        _run(8, RunStatus.COMPLETED, attacked=0.01),  # sụp
        _run(32),
        _run(4),
        _run(16),
    ]
    stop = early_stop(runs)
    assert stop is not None
    assert stop.trigger_run_id == _id(8) and stop.trigger_level == 8
    assert stop.skip_run_ids == [_id(32), _id(16)]  # level 4 < 8 vẫn chạy


def test_lowest_collapsing_level_is_trigger_and_cached_counts() -> None:
    runs = [
        _run(2, RunStatus.COMPLETED, attacked=0.3),
        _run(8, RunStatus.COMPLETED, attacked=0.01),
        _run(4, RunStatus.SKIPPED, attacked=0.02),  # trúng cache, có metric
        _run(16),
    ]
    stop = early_stop(runs)
    assert stop is not None and stop.trigger_run_id == _id(4)
    assert stop.skip_run_ids == [_id(16)]


def test_disabled_partial_and_nothing_to_skip() -> None:
    runs = [_run(8, RunStatus.COMPLETED, attacked=0.01), _run(16)]
    assert early_stop(runs, enabled=False) is None
    partial = GridRun(_id(8), 8, RunStatus.STOPPED_LIMIT, _metrics(0.01, partial=True))
    assert early_stop([partial, _run(16)]) is None
    assert early_stop([_run(8, RunStatus.COMPLETED, attacked=0.01)]) is None
    assert early_stop([_run(2, RunStatus.COMPLETED, attacked=0.4), _run(4)]) is None
