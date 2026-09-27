"""ID xác định từ nội dung: uuid5 của hash sha256 trong namespace cố định của dự án."""

from __future__ import annotations

import re
from uuid import UUID, uuid5

# Namespace cố định của AdverTest. Không bao giờ đổi: đổi sẽ làm mọi ID đã sinh không khớp.
ADVERTEST_NAMESPACE = UUID("1b0f7a52-5c1d-4e6b-9a8e-3f2d7c4b6a10")

_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")


def content_id(sha256_hex: str) -> UUID:
    """uuid5 của một hash sha256 (hex, chữ thường)."""
    if not _SHA256_HEX.fullmatch(sha256_hex):
        raise ValueError(f"Không phải sha256 hex chữ thường: {sha256_hex!r}")
    return uuid5(ADVERTEST_NAMESPACE, sha256_hex)
