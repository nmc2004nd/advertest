"""validation.md Phase 7, Thuật toán (`test_search_algorithm.py`): hàm mức sụt tổng hợp, không cần
GPU hay DB.

Bộ lái gọi `ThresholdSearch.progress` lặp lại như worker: mỗi lần lấy điểm kế tiếp, tính mức sụt
bằng hàm tổng hợp của đúng phạm vi (tập con hoặc toàn slice), thêm vào danh sách quan sát.
"""

from __future__ import annotations

import json
import random
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest

from advertest_contracts.enums import EvalScope, SearchStage, SearchStatus, ThresholdKind
from advertest_contracts.models import PrimaryParam, SearchConfig, SearchResult
from ml_core.search.algorithm import (
    Observation,
    SearchProgress,
    ThresholdSearch,
    observations_from_trajectory,
    to_search_result,
)
from ml_core.search.bounds import search_bounds

THRESHOLD = 0.2
EPS = PrimaryParam(name="eps", type="continuous", min=0, max=32, unit="1/255")
SEVERITY = PrimaryParam(
    name="severity", type="discrete", min=1, max=5, values=[1, 2, 3, 4, 5], unit="severity"
)
BIG_SLICE = 300  # lớn hơn subset_size: có giai đoạn tập con
SMALL_SLICE = 50  # không lớn hơn subset_size 100: chỉ toàn slice

Drop = Callable[[float], float | None]


def config(
    lo: float = 0, hi: float = 32, tol: float = 0.5, coarse_n: int = 4, subset_size: int = 100
) -> SearchConfig:
    return SearchConfig(
        threshold_kind=ThresholdKind.RELATIVE_DROP, threshold=THRESHOLD, lo=lo, hi=hi, tol=tol,
        coarse_n=coarse_n, subset_size=subset_size,
    )  # fmt: skip


def crossing_at(x_star: float) -> Drop:
    """Đơn điệu tăng, đúng bằng ngưỡng tại `x_star`: d(x) ≥ ngưỡng ⇔ x ≥ x_star."""
    return lambda x: THRESHOLD * x / x_star


@dataclass
class Run:
    final: SearchProgress
    observations: list[Observation]
    requests: list[tuple[float, EvalScope, SearchStage]]


def drive(search: ThresholdSearch, subset: Drop, full: Drop | None = None) -> Run:
    full = full or subset
    observations: list[Observation] = []
    requests: list[tuple[float, EvalScope, SearchStage]] = []
    while True:
        progress = search.progress(observations)
        if progress.done:
            return Run(progress, observations, requests)
        point = progress.next_point
        assert point is not None
        assert point.order == len(progress.trajectory)
        requests.append((point.level, point.scope, point.stage))
        drop = (subset if point.scope == EvalScope.SUBSET else full)(point.level)
        observations.append(Observation(point.level, point.scope, drop))


def test_found_with_tol() -> None:
    run = drive(ThresholdSearch(config(tol=0.5), EPS, BIG_SLICE), crossing_at(6.3))
    a, b = run.final.bracket
    assert run.final.status == SearchStatus.FOUND
    assert b - a <= 0.5 + 1e-12
    assert a < 6.3 <= b
    assert run.final.breaking_point == b


@pytest.mark.parametrize("seed", range(40))
def test_points_never_exceed_max_points(seed: int) -> None:
    rng = random.Random(seed)
    subset_x, full_x = rng.uniform(0.2, 31.8), rng.uniform(0.2, 31.8)
    cfg = config(tol=rng.choice([0.125, 0.5, 2.0]), coarse_n=rng.randint(3, 8))
    search = ThresholdSearch(cfg, EPS, BIG_SLICE)
    run = drive(search, crossing_at(subset_x), crossing_at(full_x))
    assert run.final.points_used == len(run.observations)
    assert run.final.points_used <= search_bounds(cfg, EPS, BIG_SLICE).max_points
    assert run.final.status in (SearchStatus.FOUND, SearchStatus.NON_MONOTONIC)


def test_never_reaches_threshold() -> None:
    run = drive(ThresholdSearch(config(), EPS, BIG_SLICE), lambda _x: 0.05)
    assert run.final.status == SearchStatus.NOT_REACHED
    assert run.final.bracket == (32, 32)
    assert run.final.breaking_point is None


def test_breaks_at_minimum() -> None:
    run = drive(ThresholdSearch(config(lo=2), EPS, BIG_SLICE), lambda _x: 0.9)
    assert run.final.status == SearchStatus.BELOW_MIN
    assert run.final.bracket == (2, 2)
    assert run.final.breaking_point is None


def test_confirmation_shifts_up_when_full_slice_breaks_later() -> None:
    run = drive(ThresholdSearch(config(), EPS, BIG_SLICE), crossing_at(6.3), crossing_at(9.1))
    a, b = run.final.bracket
    assert run.final.status == SearchStatus.FOUND
    assert a < 9.1 <= b
    assert b - a <= 0.5 + 1e-12
    full = [level for level, scope, _ in run.requests if scope == EvalScope.FULL]
    assert full and max(full) > 9.1  # đã dịch lên trên toàn slice


def test_confirmation_shifts_down_when_full_slice_breaks_earlier() -> None:
    run = drive(ThresholdSearch(config(), EPS, BIG_SLICE), crossing_at(9.1), crossing_at(6.3))
    a, b = run.final.bracket
    assert run.final.status == SearchStatus.FOUND
    assert a < 6.3 <= b
    assert b - a <= 0.5 + 1e-12


def test_dip_in_coarse_points_is_non_monotonic() -> None:
    coarse: dict[float, float] = {0: 0.0, 8: 0.15, 16: 0.10, 24: 0.5, 32: 0.9}  # 8 → 16 giảm 0.05

    def drop(x: float) -> float:
        if x in coarse:
            return coarse[x]
        return 0.15 if x < 16 else 0.10 if x < 20 else 0.5

    run = drive(ThresholdSearch(config(coarse_n=5), EPS, SMALL_SLICE), drop)
    assert run.final.status == SearchStatus.NON_MONOTONIC
    assert run.final.breaking_point is not None
    assert run.final.breaking_point == run.final.bracket[1]


def test_found_near_zero_with_default_tol() -> None:
    cfg = config(tol=(32 - 0) / 256)
    assert cfg.tol == 0.125
    run = drive(ThresholdSearch(cfg, EPS, BIG_SLICE), crossing_at(0.3))
    a, b = run.final.bracket
    assert run.final.status == SearchStatus.FOUND
    assert a < 0.3 <= b
    assert b - a <= 0.125 + 1e-12


def test_discrete_parameter() -> None:
    drop = {1: 0.0, 2: 0.05, 3: 0.15, 4: 0.3, 5: 0.6}
    cfg = config(lo=1, hi=5, tol=4 / 256)
    run = drive(ThresholdSearch(cfg, SEVERITY, SMALL_SLICE), lambda x: drop[int(x)])
    assert run.final.status == SearchStatus.FOUND
    assert run.final.bracket == (3, 4)
    assert run.final.breaking_point == 4
    assert all(level in drop for level, _, _ in run.requests)


def test_level_zero_is_synthetic_and_never_requested() -> None:
    run = drive(ThresholdSearch(config(), EPS, BIG_SLICE), crossing_at(6.3))
    zero = [entry for entry in run.final.trajectory if entry.level == 0]
    assert zero and all(entry.synthetic and entry.drop == 0.0 for entry in zero)
    assert all(level != 0 for level, _, _ in run.requests)
    assert run.final.points_used == len(run.observations)
    result = _result(ThresholdSearch(config(), EPS, BIG_SLICE), run.final)
    assert all((p.run_id is None) == p.synthetic for p in result.trajectory)


def _result(search: ThresholdSearch, progress: SearchProgress) -> SearchResult:
    run_ids = {e.order: uuid4() for e in progress.trajectory if not e.synthetic}
    return to_search_result(
        progress, search=search, experiment_id=UUID(int=1), attack_spec_id=UUID(int=2),
        run_ids=run_ids,
    )  # fmt: skip


def test_resume_from_serialized_state_at_every_stage() -> None:
    """Dừng sau mỗi điểm, tuần tự hóa `SearchResult` (JSON), dựng lại quan sát từ quỹ đạo rồi chạy
    tiếp: kết quả cuối và chuỗi điểm giống hệt chạy liền mạch."""
    cfg = config(tol=0.5)
    subset, full = crossing_at(6.3), crossing_at(9.1)
    straight = drive(ThresholdSearch(cfg, EPS, BIG_SLICE), subset, full)
    stages = {stage for _, _, stage in straight.requests}
    assert {SearchStage.COARSE, SearchStage.BISECT_SUBSET, SearchStage.CONFIRM} <= stages
    for cut in range(len(straight.observations)):
        search = ThresholdSearch(cfg, EPS, BIG_SLICE)
        interim = search.progress(straight.observations[:cut])
        saved = json.loads(_result(search, interim).model_dump_json())
        restored = observations_from_trajectory(SearchResult.model_validate(saved).trajectory)
        assert restored == straight.observations[:cut]
        resumed = ThresholdSearch(cfg, EPS, BIG_SLICE)
        again = drive_from(resumed, restored, subset, full)
        assert again.final == straight.final
        assert again.observations == straight.observations


def drive_from(search: ThresholdSearch, start: list[Observation], subset: Drop, full: Drop) -> Run:
    observations = list(start)
    while True:
        progress = search.progress(observations)
        if progress.done:
            return Run(progress, observations, [])
        point = progress.next_point
        assert point is not None
        drop = (subset if point.scope == EvalScope.SUBSET else full)(point.level)
        observations.append(Observation(point.level, point.scope, drop))


def test_slice_not_larger_than_subset_has_no_subset_stage() -> None:
    cfg = config(subset_size=100)
    run = drive(ThresholdSearch(cfg, EPS, 100), crossing_at(6.3))
    assert run.final.status == SearchStatus.FOUND
    assert all(scope == EvalScope.FULL for _, scope, _ in run.requests)
    assert all(e.scope == EvalScope.FULL for e in run.final.trajectory)
    assert SearchStage.CONFIRM not in {stage for _, _, stage in run.requests}
    assert search_bounds(cfg, EPS, 100).max_subset_points == 0
