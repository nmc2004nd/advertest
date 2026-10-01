"""Tập con của tìm ngưỡng (validation.md Phase 7, mục Tập con)."""

import random

import pytest

from advertest_contracts.hashing import sha256_of
from ml_core.search.subset import eval_image_ids_sha256, select_subset

IDS = [f"{i:06d}" for i in range(300)]


def test_same_seed_same_subset_regardless_of_input_order() -> None:
    shuffled = IDS[:]
    random.Random(7).shuffle(shuffled)
    assert select_subset(IDS, 42, 100) == select_subset(shuffled, 42, 100)


def test_subset_is_part_of_slice_without_duplicates() -> None:
    subset = select_subset(IDS, 42, 100)
    assert len(subset) == len(set(subset)) == 100
    assert set(subset) <= set(IDS)


def test_different_seed_gives_different_subset() -> None:
    assert set(select_subset(IDS, 1, 100)) != set(select_subset(IDS, 2, 100))


def test_small_slice_returns_whole_slice() -> None:
    assert sorted(select_subset(IDS[:5], 0, 100)) == IDS[:5]
    assert sorted(select_subset(IDS[:5], 0, 5)) == IDS[:5]


def test_subset_prefix_is_stable_when_size_grows() -> None:
    assert select_subset(IDS, 3, 150)[:100] == select_subset(IDS, 3, 100)


@pytest.mark.parametrize(
    ("ids", "seed", "size"), [(["a", "a"], 0, 1), (["a"], -1, 1), (["a"], 0, 0), ([""], 0, 1)]
)
def test_rejects_bad_input(ids: list[str], seed: int, size: int) -> None:
    with pytest.raises(ValueError):
        select_subset(ids, seed, size)


def test_eval_image_ids_sha256_ignores_order() -> None:
    subset = select_subset(IDS, 42, 100)
    assert eval_image_ids_sha256(subset) == eval_image_ids_sha256(reversed(subset))
    assert eval_image_ids_sha256(subset) == sha256_of(sorted(subset))


def test_subset_and_full_slice_have_different_hash() -> None:
    assert eval_image_ids_sha256(select_subset(IDS, 42, 100)) != eval_image_ids_sha256(IDS)


def test_eval_image_ids_sha256_rejects_empty_and_duplicates() -> None:
    with pytest.raises(ValueError):
        eval_image_ids_sha256([])
    with pytest.raises(ValueError):
        eval_image_ids_sha256(["a", "a"])
