"""Phân trang theo cursor (keyset) cho danh sách sắp theo `(created_at, id)` giảm dần.

Cursor là base64url của `{"t": created_at ISO, "id": uuid}` của phần tử cuối trang trước; khách
coi nó là chuỗi mờ. Keyset theo đúng thứ tự sắp nên trang không trùng, không sót kể cả khi có
dòng mới được thêm giữa hai lần gọi.
"""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import datetime
from typing import TypeVarTuple
from uuid import UUID

from sqlalchemy import Select, tuple_
from sqlalchemy.orm import InstrumentedAttribute

from backend.app.services.errors import Invalid


@dataclass(frozen=True)
class Cursor:
    created_at: datetime
    id: UUID


def encode(created_at: datetime, id_: UUID) -> str:
    raw = json.dumps({"t": created_at.isoformat(), "id": str(id_)}, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode(value: str | None) -> Cursor | None:
    if value is None:
        return None
    try:
        padded = value + "=" * (-len(value) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode()))
        cursor = Cursor(datetime.fromisoformat(data["t"]), UUID(data["id"]))
    except (ValueError, KeyError, TypeError, binascii.Error) as exc:
        raise Invalid("Cursor không hợp lệ") from exc
    if cursor.created_at.tzinfo is None:
        raise Invalid("Cursor không hợp lệ")
    return cursor


Row = TypeVarTuple("Row")


def apply(
    query: Select[*Row],
    created_at: InstrumentedAttribute[datetime],
    id_: InstrumentedAttribute[UUID],
    cursor: Cursor | None,
    limit: int,
) -> Select[*Row]:
    """Sắp giảm dần theo (created_at, id), lấy thêm 1 dòng để biết còn trang sau không."""
    if cursor is not None:
        query = query.where(tuple_(created_at, id_) < tuple_(cursor.created_at, cursor.id))
    return query.order_by(created_at.desc(), id_.desc()).limit(limit + 1)
