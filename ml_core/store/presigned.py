"""Store của worker: chỉ đọc, ghi, xóa qua presigned URL do API cấp (Phase 3).

Worker không có thông tin đăng nhập MinIO (requirements.md Phase 3, Decisions). `url_for(key,
method)` xin URL cho một khóa (worker gọi `POST /internal/worker/runs/{id}/artifact-url`; API chỉ
cấp URL trong `runs/<run_id>/`). Không có `list`.

Khác `LocalStore` và `MinioStore`, `put` không kiểm tra nội dung cũ (cần thêm một request GET):
khóa trong `runs/<run_id>/` chỉ do worker đang giữ lease của run đó ghi, và ghi lại sau gián đoạn
luôn cùng nội dung (ảnh ứng viên, checkpoint tính tất định).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

import httpx

from ml_core.store.base import KeyNotFoundError, validate_key

Method = Literal["PUT", "GET", "DELETE"]
UrlProvider = Callable[[str, Method], str]


class PresignedStore:
    def __init__(self, url_for: UrlProvider, http: httpx.Client) -> None:
        self.url_for = url_for
        self.http = http

    def put(self, key: str, data: bytes) -> None:
        response = self.http.put(self.url_for(validate_key(key), "PUT"), content=data)
        response.raise_for_status()

    def get(self, key: str) -> bytes:
        response = self.http.get(self.url_for(validate_key(key), "GET"))
        if response.status_code == httpx.codes.NOT_FOUND:
            raise KeyNotFoundError(key)
        response.raise_for_status()
        return response.content

    def exists(self, key: str) -> bool:
        with self.http.stream("GET", self.url_for(validate_key(key), "GET")) as response:
            if response.status_code == httpx.codes.NOT_FOUND:
                return False
            response.raise_for_status()
            return True

    def delete(self, key: str) -> None:
        response = self.http.delete(self.url_for(validate_key(key), "DELETE"))
        if response.status_code != httpx.codes.NOT_FOUND:
            response.raise_for_status()
