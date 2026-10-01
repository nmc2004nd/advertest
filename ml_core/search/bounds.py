"""Level quét thô và giới hạn trên số điểm đánh giá (requirements.md Phase 7, mục Thuật toán).

Backend dùng `search_bounds` để ước lượng chi phí tối đa và chặn worker tạo quá `max_points` run;
`algorithm.py` dùng cùng các hàm ở đây nên số điểm thực tế không vượt giới hạn.

Giới hạn (với `m` level thô, `s` bước chia đôi trong một ô thô):
- tập con: `m + s` (quét thô rồi chia đôi);
- toàn slice: `m + 1 + s` (xác nhận 2 đầu khoảng, dịch khoảng tối đa `m - 1` ô thô, chia đôi `s`
  bước; quyết định ở Group 1: dịch tiếp từng ô thô tới khi gãy hoặc chạm `lo`/`hi`);
- slice không lớn hơn `subset_size`: không có tập con và giai đoạn xác nhận, toàn slice `m + s`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import pairwise

from advertest_contracts.models import PrimaryParam, SearchConfig

# Sai số tương đối khi so độ rộng khoảng với `tol` (tránh thêm một bước chia đôi do làm tròn float).
WIDTH_SLACK = 1e-9


@dataclass(frozen=True)
class SearchGrid:
    """Các level hợp lệ của một lần tìm kiếm.

    `values` là null với tham số liên tục; với tham số rời rạc là các giá trị của spec trong
    `[lo, hi]`, tăng dần (chia đôi theo chỉ số trong danh sách này)."""

    lo: float
    hi: float
    tol: float
    values: tuple[float, ...] | None
    coarse: tuple[float, ...]

    @property
    def discrete(self) -> bool:
        return self.values is not None


@dataclass(frozen=True)
class SearchBounds:
    max_subset_points: int
    max_full_points: int

    @property
    def max_points(self) -> int:
        return self.max_subset_points + self.max_full_points


def search_grid(config: SearchConfig, param: PrimaryParam) -> SearchGrid:
    """Level thô: `coarse_n` level cách đều từ `lo` tới `hi`; tham số rời rạc lấy `coarse_n` giá trị
    cách đều theo chỉ số (luôn gồm giá trị nhỏ nhất và lớn nhất; ít giá trị hơn thì lấy tất cả)."""
    lo, hi = config.lo, config.hi
    if not (param.min <= lo < hi <= param.max):
        raise ValueError(
            f"[lo, hi] = [{lo}, {hi}] phải nằm trong dải của spec [{param.min}, {param.max}]"
        )
    n = config.coarse_n
    if param.type == "continuous":
        step = (hi - lo) / (n - 1)
        coarse = tuple([lo + i * step for i in range(n - 1)] + [hi])
        return SearchGrid(lo, hi, config.tol, None, coarse)
    assert param.values is not None  # PrimaryParam bắt buộc values khi discrete
    values = tuple(sorted(v for v in param.values if lo <= v <= hi))
    if len(values) < 2 or values[0] != lo or values[-1] != hi:
        raise ValueError("với tham số rời rạc, lo và hi phải là giá trị của spec và khác nhau")
    count = min(n, len(values))
    indices = sorted({round(i * (len(values) - 1) / (count - 1)) for i in range(count)})
    return SearchGrid(lo, hi, config.tol, values, tuple(values[i] for i in indices))


def bisect_steps(grid: SearchGrid) -> int:
    """`s`: số bước chia đôi tối đa trong một ô thô."""
    if grid.values is not None:
        index = {v: i for i, v in enumerate(grid.values)}
        gap = max(index[b] - index[a] for a, b in pairwise(grid.coarse))
        return math.ceil(math.log2(gap)) if gap > 1 else 0
    width = max(b - a for a, b in pairwise(grid.coarse))
    if width <= grid.tol * (1 + WIDTH_SLACK):
        return 0
    return max(0, math.ceil(math.log2(width / grid.tol) - WIDTH_SLACK))


def uses_subset(config: SearchConfig, slice_size: int) -> bool:
    """Có giai đoạn tập con: slice lớn hơn `subset_size`."""
    if slice_size < 1:
        raise ValueError(f"slice_size phải dương, nhận {slice_size}")
    return slice_size > config.subset_size


def search_bounds(config: SearchConfig, param: PrimaryParam, slice_size: int) -> SearchBounds:
    grid = search_grid(config, param)
    m, s = len(grid.coarse), bisect_steps(grid)
    if not uses_subset(config, slice_size):
        return SearchBounds(max_subset_points=0, max_full_points=m + s)
    return SearchBounds(max_subset_points=m + s, max_full_points=m + 1 + s)
