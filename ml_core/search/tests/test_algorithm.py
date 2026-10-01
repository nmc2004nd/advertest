"""Thuật toán tìm ngưỡng với hàm mức sụt tổng hợp (validation.md Phase 7, mục Thuật toán; plan
task 9). Không cần model hay GPU."""

from __future__ import annotations

import json
import random
from collections.abc import Callable
from pathlib import Path
from uuid import UUID, uuid5

import pytest

from advertest_contracts.enums import EvalScope, SearchStage, SearchStatus
from advertest_contracts.models import PrimaryParam, SearchConfig, SearchResult
from ml_core.search.algorithm import (
    Observation,
    SearchProgress,
    ThresholdSearch,
    observations_from_trajectory,
    to_search_result,
)

Drop = Callable[[float], float | None]
NS = UUID("6f1c2b8e-7a0d-4c55-9e3a-2b7d1f0c9a18")
MOCKS = Path(__file__).resolve().parents[3] / "contracts" / "mocks"

EPS = PrimaryParam(name="eps", type="continuous", min=0, max=32, unit="1/255")
SEVERITY = PrimaryParam(
    name="severity", type="discrete", min=1, max=5, values=[1, 2, 3, 4, 5], unit="severity"
)
SLICE = 300


def _config(**overrides: object) -> SearchConfig:
    data: dict[str, object] = {
        "threshold_kind": "relative_drop",
        "threshold": 0.2,
        "lo": 0,
        "hi": 32,
        "tol": 0.5,
        "coarse_n": 4,
        "subset_size": 100,
    }
    data.update(overrides)
    return SearchConfig.model_validate(data)


def crossing(x_star: float, threshold: float = 0.2) -> Drop:
    """Hàm đơn điệu tăng, d(x) ≥ ngưỡng khi và chỉ khi x ≥ x_star."""
    return lambda x: min(1.0, threshold * x / x_star)


def noisy(x_star: float, noise: float, seed: int) -> Drop:
    """Hàm có nhiễu cố định theo level (không đơn điệu); tập con và toàn slice dùng seed khác."""
    base = crossing(max(x_star, 1e-6))

    def drop(x: float) -> float:
        return min(1.0, base(x) or 0.0) + random.Random(f"{x!r}/{seed}").uniform(-noise, noise)

    return drop


def run(
    search: ThresholdSearch, subset: Drop, full: Drop | None = None
) -> tuple[SearchProgress, list[Observation]]:
    """Chạy tới khi kết thúc, mỗi lần chỉ đưa thêm một quan sát (như worker)."""
    full = full or subset
    observations: list[Observation] = []
    while True:
        progress = search.progress(observations)
        if progress.done:
            return progress, observations
        request = progress.next_point
        assert request is not None
        assert request.order == len(progress.trajectory)
        assert request.level != 0, "level 0 là synthetic, không được tạo run"
        drop = (subset if request.scope == EvalScope.SUBSET else full)(request.level)
        observations.append(Observation(request.level, request.scope, drop))


def count(observations: list[Observation], scope: EvalScope) -> int:
    return sum(1 for o in observations if o.scope == scope)


# ---------------------------------------------------------------- kết quả cơ bản


def test_monotone_crossing_found_within_tol() -> None:
    search = ThresholdSearch(_config(), EPS, SLICE)
    progress, _ = run(search, crossing(6.3))
    assert progress.status == SearchStatus.FOUND
    a, b = progress.bracket
    assert b - a <= 0.5
    assert a < 6.3 <= b
    assert progress.breaking_point == b
    assert progress.stage == SearchStage.DONE


def test_small_eps_crossing_with_default_tol() -> None:
    # tol mặc định (hi - lo) / 256 = 0.125; PGD trên KITTI gãy dưới 1/255 (kickoff Phase 7).
    search = ThresholdSearch(_config(tol=32 / 256, coarse_n=5), EPS, SLICE)
    progress, _ = run(search, crossing(0.3))
    a, b = progress.bracket
    assert progress.status == SearchStatus.FOUND
    assert a < 0.3 <= b
    assert b - a <= 0.125


def test_not_reached() -> None:
    search = ThresholdSearch(_config(), EPS, SLICE)
    progress, observations = run(search, lambda x: 0.1)
    assert progress.status == SearchStatus.NOT_REACHED
    assert progress.bracket == (32, 32)
    assert progress.breaking_point is None
    assert observations[-1] == Observation(32, EvalScope.FULL, 0.1)


def test_below_min() -> None:
    search = ThresholdSearch(_config(lo=2), EPS, SLICE)
    progress, observations = run(search, lambda x: 0.9)
    assert progress.status == SearchStatus.BELOW_MIN
    assert progress.bracket == (2, 2)
    assert observations[-1] == Observation(2, EvalScope.FULL, 0.9)


def test_lo_zero_is_never_below_min() -> None:
    # Level 0 có mức sụt 0 theo định nghĩa: gãy ở mọi level dương → điểm gãy sát 0.
    search = ThresholdSearch(_config(), EPS, SLICE)
    progress, _ = run(search, lambda x: 0.9)
    assert progress.status == SearchStatus.FOUND
    assert progress.bracket[0] == 0 and progress.bracket[1] <= 0.5


# ---------------------------------------------------------------- tập con khác toàn slice


def test_shift_up_when_full_slice_breaks_later() -> None:
    search = ThresholdSearch(_config(), EPS, SLICE)
    progress, observations = run(search, crossing(6.3), crossing(9.1))
    a, b = progress.bracket
    assert progress.status == SearchStatus.FOUND
    assert a < 9.1 <= b and b - a <= 0.5
    assert len(observations) <= search.bounds.max_points


def test_shift_down_when_full_slice_breaks_earlier() -> None:
    search = ThresholdSearch(_config(), EPS, SLICE)
    progress, observations = run(search, crossing(9.1), crossing(6.3))
    a, b = progress.bracket
    assert progress.status == SearchStatus.FOUND
    assert a < 6.3 <= b and b - a <= 0.5
    assert len(observations) <= search.bounds.max_points


@pytest.mark.parametrize(("subset_x", "full_x"), [(6.3, 25.0), (25.0, 3.0), (6.3, 40.0)])
def test_shift_across_several_coarse_cells(subset_x: float, full_x: float) -> None:
    search = ThresholdSearch(_config(), EPS, SLICE)
    progress, observations = run(search, crossing(subset_x), crossing(full_x))
    if full_x > 32:
        assert progress.status == SearchStatus.NOT_REACHED
    else:
        a, b = progress.bracket
        assert a < full_x <= b and b - a <= 0.5
    assert count(observations, EvalScope.FULL) <= search.bounds.max_full_points


def test_confirm_lo_not_broken_on_full_slice_searches_up() -> None:
    search = ThresholdSearch(_config(lo=2), EPS, SLICE)
    progress, _ = run(search, lambda x: 0.9, crossing(12.0))
    a, b = progress.bracket
    assert progress.status == SearchStatus.FOUND
    assert a < 12.0 <= b


def test_confirm_hi_broken_on_full_slice_searches_down() -> None:
    search = ThresholdSearch(_config(), EPS, SLICE)
    progress, _ = run(search, lambda x: 0.1, crossing(20.0))
    a, b = progress.bracket
    assert progress.status == SearchStatus.FOUND
    assert a < 20.0 <= b


def test_points_never_exceed_bounds() -> None:
    rng = random.Random(20261001)
    for _ in range(400):
        coarse_n = rng.randint(3, 8)
        hi = rng.choice([0.9, 16.0, 32.0])
        tol = hi / rng.choice([8, 32, 64, 256, 1000])
        config = _config(hi=hi, tol=tol, coarse_n=coarse_n, subset_size=100)
        param = PrimaryParam(name="x", type="continuous", min=0, max=hi, unit="u")
        search = ThresholdSearch(config, param, SLICE)
        sub_x, full_x = rng.uniform(-0.1, 1.2) * hi, rng.uniform(-0.1, 1.2) * hi
        noise = rng.uniform(0, 0.3)
        subset, full = noisy(sub_x, noise, 1), noisy(full_x, noise, 2)
        progress, observations = run(search, subset, full)
        assert progress.done
        assert count(observations, EvalScope.SUBSET) <= search.bounds.max_subset_points
        assert count(observations, EvalScope.FULL) <= search.bounds.max_full_points
        assert progress.points_used == len(observations) <= search.bounds.max_points
        low, high = progress.bracket
        assert low <= high


# ---------------------------------------------------------------- không đơn điệu


def test_coarse_dip_marks_non_monotonic_but_keeps_breaking_point() -> None:
    coarse: dict[float, float] = {0: 0.0, 8: 0.1, 16: 0.05, 24: 0.5, 32: 0.9}

    def drop(x: float) -> float:
        return coarse.get(x, 0.1 if x < 20 else 0.5)

    search = ThresholdSearch(_config(coarse_n=5), EPS, SLICE)
    progress, _ = run(search, drop)
    assert progress.status == SearchStatus.NON_MONOTONIC
    assert progress.non_monotonic
    assert progress.breaking_point is not None
    a, b = progress.bracket
    assert 16 <= a < 20 <= b <= 24


def test_small_dip_within_tolerance_is_monotonic() -> None:
    coarse: dict[float, float] = {8: 0.1, 16: 0.085, 24: 0.5, 32: 0.9}
    search = ThresholdSearch(_config(coarse_n=5), EPS, SLICE)
    progress, _ = run(search, lambda x: coarse.get(x, 0.1 if x < 20 else 0.5))
    assert progress.status == SearchStatus.FOUND


def test_conflicting_confirmation_shifts_down_and_flags() -> None:
    def full(x: float) -> float:
        if x < 3.0:
            return 0.1
        return 0.3 if x <= 6.25 else 0.1

    search = ThresholdSearch(_config(), EPS, SLICE)
    progress, _ = run(search, crossing(6.3), full)
    assert progress.status == SearchStatus.NON_MONOTONIC
    a, b = progress.bracket
    assert a < 3.0 <= b


# ---------------------------------------------------------------- tham số rời rạc


@pytest.mark.parametrize("coarse_n", [3, 5])
def test_discrete_crossing_between_three_and_four(coarse_n: int) -> None:
    drops = {1: 0.05, 2: 0.1, 3: 0.15, 4: 0.3, 5: 0.4}
    search = ThresholdSearch(_config(lo=1, hi=5, coarse_n=coarse_n), SEVERITY, SLICE)
    progress, observations = run(search, lambda x: drops[int(x)])
    assert progress.status == SearchStatus.FOUND
    assert progress.bracket == (3, 4)
    assert progress.breaking_point == 4
    assert all(o.level in drops for o in observations)
    assert not any(entry.synthetic for entry in progress.trajectory)


# ---------------------------------------------------------------- điểm synthetic


def test_level_zero_is_synthetic_without_run() -> None:
    search = ThresholdSearch(_config(), EPS, SLICE)
    progress, observations = run(search, crossing(6.3))
    first = progress.trajectory[0]
    assert (first.level, first.synthetic, first.drop, first.order) == (0, True, 0.0, 0)
    assert all(o.level != 0 for o in observations)
    assert progress.points_used == len(observations)


# ---------------------------------------------------------------- chạy tiếp sau gián đoạn


def _fingerprint(progress: SearchProgress) -> tuple[object, ...]:
    return (progress.status, progress.bracket, progress.breaking_point, progress.trajectory)


@pytest.mark.parametrize(("subset_x", "full_x"), [(6.3, 6.3), (6.3, 9.1), (9.1, 6.3)])
def test_resume_from_any_prefix_matches_uninterrupted(subset_x: float, full_x: float) -> None:
    search = ThresholdSearch(_config(), EPS, SLICE)
    final, observations = run(search, crossing(subset_x), crossing(full_x))
    for k in range(len(observations)):
        # Worker mới chỉ có SearchResult tạm thời sau k điểm (Group 0: dựng lại từ trajectory).
        interim = search.progress(observations[:k])
        result = to_search_result(
            interim,
            search=search,
            experiment_id=NS,
            attack_spec_id=NS,
            run_ids={e.order: uuid5(NS, str(e.order)) for e in interim.trajectory},
        )
        restored = SearchResult.model_validate_json(result.model_dump_json())
        replayed = observations_from_trajectory(restored.trajectory)
        assert replayed == observations[:k]
        resumed = search.progress(replayed)
        assert resumed.next_point is not None
        assert (resumed.next_point.level, resumed.next_point.scope) == (
            observations[k].level,
            observations[k].scope,
        )
        assert _fingerprint(search.progress([*replayed, *observations[k:]])) == _fingerprint(final)


def test_interim_stage_and_bracket() -> None:
    search = ThresholdSearch(_config(tol=32 / 256, coarse_n=5), EPS, SLICE)
    _, observations = run(search, crossing(0.3), crossing(0.3))
    assert search.progress(observations[:2]).stage == SearchStage.COARSE
    after_coarse = search.progress(observations[:4])
    assert after_coarse.stage == SearchStage.BISECT_SUBSET
    assert after_coarse.bracket == (0, 8)
    after_three_bisects = search.progress(observations[:7])
    assert after_three_bisects.bracket == (0, 1)
    confirm = next(i for i, o in enumerate(observations) if o.scope == EvalScope.FULL)
    assert search.progress(observations[:confirm]).stage == SearchStage.CONFIRM


def test_replays_contract_mock_found() -> None:
    mock = SearchResult.model_validate_json((MOCKS / "search_result" / "found.json").read_text())
    config = _config(tol=0.125, coarse_n=5)
    search = ThresholdSearch(config, EPS, SLICE)
    progress = search.progress(observations_from_trajectory(mock.trajectory))
    assert progress.status == mock.status
    assert progress.bracket == mock.bracket
    assert [(e.level, e.scope, e.synthetic) for e in progress.trajectory] == [
        (p.level, p.scope, p.synthetic) for p in mock.trajectory
    ]


# ---------------------------------------------------------------- slice nhỏ


def test_small_slice_has_no_subset_points_or_confirmation() -> None:
    search = ThresholdSearch(_config(subset_size=100), EPS, 80)
    progress, observations = run(search, crossing(6.3))
    assert progress.status == SearchStatus.FOUND
    assert all(o.scope == EvalScope.FULL for o in observations)
    assert len(observations) <= search.bounds.max_full_points
    assert search.bounds.max_subset_points == 0
    stages = {search.progress(observations[:k]).stage for k in range(len(observations))}
    assert SearchStage.CONFIRM not in stages and SearchStage.BISECT_SUBSET not in stages


def test_small_slice_below_min_and_not_reached_skip_confirmation() -> None:
    search = ThresholdSearch(_config(lo=2, subset_size=100), EPS, 50)
    progress, observations = run(search, lambda x: 0.9)
    assert progress.status == SearchStatus.BELOW_MIN
    assert len(observations) == len(search.grid.coarse)


# ---------------------------------------------------------------- dừng, lỗi, đầu vào sai


def test_stop_gives_stopped_limit_with_known_bracket() -> None:
    search = ThresholdSearch(_config(), EPS, SLICE)
    _, observations = run(search, crossing(6.3))
    stopped = search.progress(observations[:5], stop=True)
    assert stopped.status == SearchStatus.STOPPED_LIMIT
    assert stopped.stage == SearchStage.DONE
    assert stopped.next_point is None
    assert stopped.bracket == search.progress(observations[:5]).bracket
    assert stopped.breaking_point is None


def test_stop_after_finish_keeps_result() -> None:
    search = ThresholdSearch(_config(), EPS, SLICE)
    final, observations = run(search, crossing(6.3))
    assert search.progress(observations, stop=True, failure="x").status == final.status


def test_missing_drop_fails_with_message() -> None:
    search = ThresholdSearch(_config(class_filter="truck"), EPS, SLICE)
    progress, _ = run(search, lambda x: None)
    assert progress.status == SearchStatus.FAILED
    assert progress.message is not None and "truck" in progress.message
    assert progress.trajectory[-1].drop is None


def test_worker_failure_message() -> None:
    search = ThresholdSearch(_config(), EPS, SLICE)
    progress = search.progress([], failure="Lỗi không phục hồi khi chạy attack")
    assert progress.status == SearchStatus.FAILED
    assert progress.message == "Lỗi không phục hồi khi chạy attack"
    assert progress.bracket == (0, 32)


def test_rejects_mismatched_or_extra_observations() -> None:
    search = ThresholdSearch(_config(), EPS, SLICE)
    _, observations = run(search, crossing(6.3))
    with pytest.raises(ValueError, match="không khớp"):
        search.progress([Observation(5.0, EvalScope.SUBSET, 0.1)])
    with pytest.raises(ValueError, match="thừa"):
        search.progress([*observations, observations[-1]])


# ---------------------------------------------------------------- SearchResult


def test_search_results_validate_for_every_status() -> None:
    cases: list[tuple[ThresholdSearch, Drop, Drop]] = [
        (ThresholdSearch(_config(), EPS, SLICE), crossing(6.3), crossing(6.3)),
        (ThresholdSearch(_config(), EPS, SLICE), lambda x: 0.1, lambda x: 0.1),
        (ThresholdSearch(_config(lo=2), EPS, SLICE), lambda x: 0.9, lambda x: 0.9),
    ]
    statuses = set()
    for search, subset, full in cases:
        progress, _ = run(search, subset, full)
        result = to_search_result(
            progress,
            search=search,
            experiment_id=NS,
            attack_spec_id=NS,
            run_ids={e.order: uuid5(NS, str(e.order)) for e in progress.trajectory},
        )
        statuses.add(result.status)
        assert result.points_used <= result.max_points
        json.loads(result.model_dump_json())
    assert statuses == {SearchStatus.FOUND, SearchStatus.NOT_REACHED, SearchStatus.BELOW_MIN}


# ------------------------------------------------ khoảng tạm thời khi xác nhận (review Group 1, #1)


def _subset_done_index(observations: list[Observation]) -> int:
    return next(i for i, o in enumerate(observations) if o.scope == EvalScope.FULL)


@pytest.mark.parametrize(("x_star", "tol", "coarse_n"), [(0.3, 0.125, 5), (6.3, 0.5, 4)])
def test_interim_bracket_does_not_widen_when_confirming(
    x_star: float, tol: float, coarse_n: int
) -> None:
    search = ThresholdSearch(_config(tol=tol, coarse_n=coarse_n), EPS, SLICE)
    final, observations = run(search, crossing(x_star))
    k = _subset_done_index(observations)
    sub_lo, sub_hi = search.progress(observations[:k]).bracket
    assert sub_hi - sub_lo <= tol
    for i in range(k, len(observations)):
        low, high = search.progress(observations[:i]).bracket
        assert sub_lo <= low <= high <= sub_hi, (i, low, high)
        assert search.progress(observations[:i], stop=True).bracket == (low, high)
    assert final.bracket == (sub_lo, sub_hi)


def test_interim_bracket_while_shifting_up_is_valid_and_bounded() -> None:
    search = ThresholdSearch(_config(), EPS, SLICE)
    _, observations = run(search, crossing(6.3), crossing(25.0))
    for i in range(_subset_done_index(observations), len(observations)):
        progress = search.progress(observations[:i])
        low, high = progress.bracket
        assert low <= high
        assert (low, high) != (0, 32), i
