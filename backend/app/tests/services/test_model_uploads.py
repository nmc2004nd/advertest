"""Kiểm header safetensors khi đăng ký model qua web (mission.md nguyên tắc 10)."""

from __future__ import annotations

import io
import json
import pickle
import struct
import zipfile

import numpy as np
import pytest
from safetensors.numpy import save

from backend.app.services.model_uploads import is_safetensors


def _raw(header: object, body: bytes = b"") -> bytes:
    encoded = json.dumps(header).encode()
    return struct.pack("<Q", len(encoded)) + encoded + body


def test_real_safetensors_accepted() -> None:
    data = save({"w": np.zeros((2, 3), dtype=np.float32), "b": np.ones(3, dtype=np.float32)})
    assert is_safetensors(data)


def _zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("archive/data.pkl", pickle.dumps({"w": [1, 2]}))
    return buffer.getvalue()


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"short",
        pickle.dumps({"weights": [1, 2, 3]}),
        _zip(),
        b"khong phai safetensors",
        struct.pack("<Q", 10**12) + b"{}",  # độ dài header vượt file
        _raw([1, 2]),  # không phải object
        _raw({}),  # không có tensor nào
        _raw({"__metadata__": {"a": "b"}}),
        _raw({"w": {"dtype": "F32", "shape": [2], "data_offsets": [0, 8]}}, b"1234"),  # vượt body
        _raw({"w": {"dtype": "F32", "shape": [-1], "data_offsets": [0, 0]}}),
        _raw({"w": {"shape": [1], "data_offsets": [0, 4]}}, b"1234"),  # thiếu dtype
        struct.pack("<Q", 4) + b"\xff\xfe{}",  # không phải UTF-8
    ],
)
def test_other_content_rejected(data: bytes) -> None:
    assert not is_safetensors(data)


def test_metadata_alongside_tensor_accepted() -> None:
    header = {
        "__metadata__": {"format": "pt"},
        "w": {"dtype": "F32", "shape": [1], "data_offsets": [0, 4]},
    }
    assert is_safetensors(_raw(header, b"\x00\x00\x80\x3f"))
