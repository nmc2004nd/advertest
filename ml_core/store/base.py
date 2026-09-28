"""Interface chung của kho artifact."""

from __future__ import annotations

import re
from typing import Protocol

# Key là đường dẫn tương đối kiểu POSIX: các đoạn gồm chữ, số, `.`, `_`, `-`, cách nhau bởi `/`.
_SEGMENT = re.compile(r"^[A-Za-z0-9._-]+$")


class KeyNotFoundError(KeyError):
    """Key không có trong store."""


class KeyConflictError(ValueError):
    """Ghi nội dung khác vào key đã có. Artifact là bất biến (mission.md nguyên tắc 3)."""


def validate_key(key: str) -> str:
    """Trả lại key nếu hợp lệ; báo `ValueError` nếu key có thể thoát khỏi gốc của store."""
    segments = key.split("/")
    if not key or any(not _SEGMENT.fullmatch(s) or s in {".", ".."} for s in segments):
        raise ValueError(f"Key không hợp lệ: {key!r}")
    return key


class ArtifactStore(Protocol):
    """Kho artifact bất biến theo key.

    `put` cùng nội dung vào key đã có là no-op; nội dung khác báo `KeyConflictError`.
    """

    def put(self, key: str, data: bytes) -> None: ...

    def get(self, key: str) -> bytes: ...

    def exists(self, key: str) -> bool: ...

    def list(self, prefix: str = "") -> list[str]:
        """Các key bắt đầu bằng `prefix`, đã sắp xếp."""
        ...
