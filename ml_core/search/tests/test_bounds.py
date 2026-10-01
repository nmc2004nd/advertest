"""Level thô và giới hạn trên số điểm (requirements.md Phase 7, mục Thuật toán; plan task 6)."""

import pytest

from advertest_contracts.models import PrimaryParam, SearchConfig
from ml_core.search.bounds import bisect_steps, search_bounds, search_grid, uses_subset

EPS = PrimaryParam(name="eps", type="continuous", min=0, max=32, unit="1/255")
SEVERITY = PrimaryParam(
    name="severity", type="discrete", min=1, max=5, values=[1, 2, 3, 4, 5], unit="severity"
)


def _config(**overrides: object) -> SearchConfig:
    data: dict[str, object] = {
        "threshold_kind": "relative_drop",
        "threshold": 0.2,
        "lo": 0,
        "hi": 32,
        "tol": 0.125,
        "coarse_n": 5,
        "subset_size": 100,
    }
    data.update(overrides)
    return SearchConfig.model_validate(data)


def test_continuous_coarse_levels_are_even_and_end_at_hi() -> None:
    grid = search_grid(_config(), EPS)
    assert grid.coarse == (0, 8, 16, 24, 32)
    assert not grid.discrete
    odd = search_grid(_config(coarse_n=4), EPS)
    assert odd.coarse[0] == 0 and odd.coarse[-1] == 32 and len(odd.coarse) == 4


def test_pgd_default_bounds() -> None:
    # W = 8, tol = 0.125 → s = 6; tập con 5 + 6, toàn slice 5 + 1 + 6.
    bounds = search_bounds(_config(), EPS, 300)
    assert (bounds.max_subset_points, bounds.max_full_points, bounds.max_points) == (11, 12, 23)


def test_bisect_steps_continuous() -> None:
    assert bisect_steps(search_grid(_config(tol=0.5, coarse_n=4), EPS)) == 5  # 10.67 / 0.5 = 21.3
    assert bisect_steps(search_grid(_config(tol=8, coarse_n=5), EPS)) == 0
    assert bisect_steps(search_grid(_config(tol=7.9, coarse_n=5), EPS)) == 1


def test_discrete_coarse_picks_by_index_with_min_and_max() -> None:
    config = _config(lo=1, hi=5, tol=0.5, coarse_n=3)
    grid = search_grid(config, SEVERITY)
    assert grid.values == (1, 2, 3, 4, 5)
    assert grid.coarse == (1, 3, 5)
    assert bisect_steps(grid) == 1
    assert search_bounds(config, SEVERITY, 300).max_points == (3 + 1) + (3 + 1 + 1)


def test_discrete_all_values_when_coarse_n_exceeds_values() -> None:
    config = _config(lo=1, hi=5, tol=0.5, coarse_n=8)
    grid = search_grid(config, SEVERITY)
    assert grid.coarse == (1, 2, 3, 4, 5)
    assert bisect_steps(grid) == 0
    assert search_bounds(config, SEVERITY, 300).max_points == 5 + 6


def test_discrete_sub_range() -> None:
    grid = search_grid(_config(lo=2, hi=4, tol=0.5, coarse_n=3), SEVERITY)
    assert grid.values == (2, 3, 4) and grid.coarse == (2, 3, 4)


def test_small_slice_has_no_subset_or_confirmation() -> None:
    config = _config(subset_size=100)
    assert not uses_subset(config, 100)
    assert uses_subset(config, 101)
    bounds = search_bounds(config, EPS, 100)
    assert (bounds.max_subset_points, bounds.max_full_points) == (0, 5 + 6)


@pytest.mark.parametrize(
    ("config", "param"),
    [
        (_config(lo=-1), EPS),
        (_config(hi=40), EPS),
        (_config(lo=1.5, hi=5, tol=0.5), SEVERITY),
    ],
)
def test_rejects_range_outside_spec(config: SearchConfig, param: PrimaryParam) -> None:
    with pytest.raises(ValueError):
        search_grid(config, param)


def test_rejects_non_positive_slice() -> None:
    with pytest.raises(ValueError):
        uses_subset(_config(), 0)
