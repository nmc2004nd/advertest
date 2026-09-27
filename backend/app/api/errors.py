"""Lỗi dùng chung của API khung.

Phase 0 task 21 sẽ gắn body thống nhất `ErrorResponse` (chờ đề xuất contract 001).
"""

from __future__ import annotations

from typing import NoReturn

from fastapi import HTTPException, status


def not_implemented() -> NoReturn:
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="not_implemented")
