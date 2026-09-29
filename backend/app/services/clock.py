"""Đồng hồ UTC truyền được vào service (test lease hết hạn không phải chờ thật)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

Clock = Callable[[], datetime]


def utcnow() -> datetime:
    return datetime.now(UTC)
