"""Chỉ mục id → sha: CLI nhận id (uuid), store lưu theo sha.

Mọi id là `content_id(sha)` (tech-stack.md mục 4.1), nên không suy ngược được sha từ id;
chỉ mục lưu ở `index/<kind>/<id>` với nội dung là sha hex.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from advertest_contracts.ids import content_id
from ml_core.store.base import ArtifactStore, KeyNotFoundError

IdKind = Literal["dataset", "slice", "mapping", "model"]


def _key(kind: IdKind, id_: UUID) -> str:
    return f"index/{kind}/{id_}"


def register_id(store: ArtifactStore, kind: IdKind, sha256_hex: str) -> UUID:
    """Ghi chỉ mục cho `sha256_hex` và trả về id của nó. Gọi lại nhiều lần là an toàn."""
    id_ = content_id(sha256_hex)
    store.put(_key(kind, id_), sha256_hex.encode())
    return id_


def resolve_id(store: ArtifactStore, kind: IdKind, id_: UUID) -> str:
    """Sha của id; báo `KeyNotFoundError` với thông báo dễ hiểu nếu id chưa có."""
    try:
        return store.get(_key(kind, id_)).decode()
    except KeyNotFoundError:
        raise KeyNotFoundError(f"Không tìm thấy {kind} có id {id_} trong store") from None
