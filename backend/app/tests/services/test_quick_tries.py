"""Kiểm ảnh thử nhanh và URL ảnh của thử nhanh (requirements.md Phase R2, mục Thử nhanh)."""

from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from PIL import Image

from backend.app.services import artifacts
from backend.app.services.errors import Invalid
from backend.app.services.quick_tries import (
    ORPHAN_MIN_AGE,
    clean_key,
    image_extension,
    level_key,
    original_key,
    orphan_keys,
    prefix,
)

NOW = datetime(2026, 10, 10, tzinfo=UTC)


def _image(width: int, height: int, fmt: str) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (10, 20, 30)).save(buffer, format=fmt)
    return buffer.getvalue()


@pytest.mark.parametrize(("fmt", "extension"), [("PNG", "png"), ("JPEG", "jpg")])
def test_png_and_jpeg_accepted(fmt: str, extension: str) -> None:
    assert image_extension(_image(64, 32, fmt)) == extension


@pytest.mark.parametrize(
    "data",
    [
        b"khong phai anh",
        _image(16, 16, "GIF"),
        _image(16, 16, "BMP"),
        _image(4097, 4, "PNG"),
        _image(4, 4097, "PNG"),
        _image(64, 64, "PNG")[:40],  # PNG cắt cụt
    ],
)
def test_other_images_rejected(data: bytes) -> None:
    with pytest.raises(Invalid):
        image_extension(data)


def test_size_limit() -> None:
    with pytest.raises(Invalid, match="10 MB"):
        image_extension(b"\x89PNG" + bytes(10 * 1024 * 1024))


def test_longest_side_at_limit_accepted() -> None:
    assert image_extension(_image(4096, 2, "PNG")) == "png"


def test_result_images_servable_original_never() -> None:
    quick_try_id = uuid4()
    for key in (clean_key(quick_try_id), level_key(quick_try_id, 3)):
        token, _ = artifacts.issue(key, NOW)
        assert artifacts.verify(token, NOW) == key
    with pytest.raises(ValueError):
        artifacts.issue(original_key(quick_try_id, "png"), NOW)
    assert not artifacts.servable(original_key(quick_try_id, "jpg"))
    assert not artifacts.servable(f"datasets/{quick_try_id}.png")
    assert artifacts.servable(f"runs/{quick_try_id}/cases/a.png")


# ---------------------------------------------------------------- object mồ côi (Phase R3)


def test_orphan_keys_need_dead_quick_try_and_age() -> None:
    now = NOW
    old = now - ORPHAN_MIN_AGE - timedelta(seconds=1)
    fresh = now - ORPHAN_MIN_AGE
    live, dead = uuid4(), uuid4()
    objects = [
        (prefix(live) + "level_0.png", old),  # lượt còn sống: giữ
        (prefix(dead) + "level_0.png", old),
        (prefix(dead) + "level_1.png", fresh),  # chưa quá 30 phút: giữ
        ("quick-tries/khong-phai-uuid/a.png", old),
    ]
    assert orphan_keys(objects, {live}, now) == [
        prefix(dead) + "level_0.png",
        "quick-tries/khong-phai-uuid/a.png",
    ]
