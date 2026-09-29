"""`ArtifactStore` trên MinIO (API S3), dùng ở phía backend (Phase 3).

Client S3 được truyền vào (backend tạo bằng boto3 với thông tin đăng nhập của nó): `ml_core`
không import client MinIO có thông tin đăng nhập (`validation.md` Phase 3, ranh giới kiến trúc).
Mỗi store ứng với một bucket (`models`, `datasets`, `artifacts`).
"""

from __future__ import annotations

import hashlib
from typing import Any, Protocol

from ml_core.store.base import KeyConflictError, KeyNotFoundError, validate_key

_NOT_FOUND = {"404", "NoSuchKey", "NotFound"}


class S3Client(Protocol):
    """Phần của client S3 (boto3) mà `MinioStore` dùng."""

    def put_object(self, *, Bucket: str, Key: str, Body: bytes) -> Any: ...

    def get_object(self, *, Bucket: str, Key: str) -> Any: ...

    def head_object(self, *, Bucket: str, Key: str) -> Any: ...

    def delete_object(self, *, Bucket: str, Key: str) -> Any: ...

    def get_paginator(self, operation_name: str) -> Any: ...


def _is_not_found(exc: Exception) -> bool:
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return False
    return str(response.get("Error", {}).get("Code")) in _NOT_FOUND


class MinioStore:
    def __init__(self, client: S3Client, bucket: str) -> None:
        self.client = client
        self.bucket = bucket

    def _head(self, key: str) -> dict[str, Any] | None:
        try:
            head: dict[str, Any] = self.client.head_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            if _is_not_found(exc):
                return None
            raise
        return head

    def put(self, key: str, data: bytes) -> None:
        """Bất biến như `LocalStore`: cùng nội dung là no-op, khác nội dung báo xung đột."""
        validate_key(key)
        head = self._head(key)
        if head is not None:
            etag = str(head.get("ETag", "")).strip('"')
            if etag != hashlib.md5(data).hexdigest() and self.get(key) != data:
                raise KeyConflictError(f"Key {key!r} đã có với nội dung khác")
            return
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data)

    def get(self, key: str) -> bytes:
        validate_key(key)
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            if _is_not_found(exc):
                raise KeyNotFoundError(key) from None
            raise
        body: bytes = response["Body"].read()
        return body

    def exists(self, key: str) -> bool:
        return self._head(validate_key(key)) is not None

    def delete(self, key: str) -> None:
        """Chỉ dùng cho dữ liệu chưa phải kết quả (ứng viên failure case)."""
        self.client.delete_object(Bucket=self.bucket, Key=validate_key(key))

    def list(self, prefix: str = "") -> list[str]:
        paginator = self.client.get_paginator("list_objects_v2")
        keys = [
            item["Key"]
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix)
            for item in page.get("Contents", [])
        ]
        return sorted(keys)
