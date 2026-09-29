"""`ShaCacheLoader`: ảnh đọc từ cache theo sha256 cho kết quả như `SliceLoader`."""

from __future__ import annotations

import shutil
from pathlib import Path
from uuid import UUID

import numpy as np
import pytest

from ml_core.data.loader import ImageNotFoundError, SliceLoader
from ml_core.runner.cache_loader import ShaCacheLoader, cached_image_path
from ml_core.runner.tests.test_run import Base, _build
from ml_core.store import LocalStore


@pytest.fixture(scope="module")
def base(tmp_path_factory: pytest.TempPathFactory) -> Base:
    return _build(tmp_path_factory.mktemp("cache-loader"), supports_gradients=True)


def test_cache_loader_matches_slice_loader(base: Base, tmp_path: Path) -> None:
    store = LocalStore(base.root)
    source = SliceLoader.from_ids(store, UUID(base.slice_id), UUID(base.mapping_id))
    image_dir = tmp_path / "images"
    cache = ShaCacheLoader(store, source.slice, source.mapping, source.card, image_dir)
    assert cache.missing_images() == source.slice.image_ids
    with pytest.raises(ImageNotFoundError, match="chưa có"):
        cache.load(source.slice.image_ids[0])

    image_dir.mkdir()
    for image in source.manifest.images:
        root = source.roots[0]
        shutil.copy(root / image.file_name, cached_image_path(image_dir, image.sha256))
    assert cache.missing_images() == []
    expected = next(source.batches(3))
    got = next(cache.batches(3))
    assert got.image_ids == expected.image_ids
    assert np.array_equal(got.images, expected.images)
    for a, b in zip(got.targets, expected.targets, strict=True):
        assert np.array_equal(a["boxes"], b["boxes"]) and np.array_equal(a["labels"], b["labels"])

    first = source.slice.image_ids[0]
    cached_image_path(image_dir, cache.image_sha256(first)).write_bytes(b"broken")
    with pytest.raises(ImageNotFoundError, match="sai sha256"):
        cache.load(first)
