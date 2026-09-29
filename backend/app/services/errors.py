"""Lỗi nghiệp vụ. Tầng API đổi sang HTTP: NotFound → 404, Forbidden → 403, Conflict → 409,
Invalid → 422; `InvalidConfig` và `QueueLimitReached` mang mã lỗi riêng (Phase 5)."""

from __future__ import annotations

from collections.abc import Sequence

from advertest_contracts.enums import ErrorCode
from advertest_contracts.models import FieldError


class ServiceError(Exception):
    """Lỗi nghiệp vụ; thông điệp an toàn để trả cho client."""


class NotFound(ServiceError):
    pass


class Forbidden(ServiceError):
    pass


class Conflict(ServiceError):
    pass


class Invalid(ServiceError):
    pass


class InvalidConfig(Invalid):
    """Cấu hình experiment sai (422), kèm đường dẫn từng trường sai. `code` là
    `not_supported_yet` khi có tính năng chưa hỗ trợ (mode = search), ngược lại
    `invalid_request`."""

    def __init__(self, message: str, fields: Sequence[FieldError], code: ErrorCode) -> None:
        super().__init__(message)
        self.fields = list(fields)
        self.code = code


class QueueLimitReached(Conflict):
    """Người dùng đã có đủ số experiment đang chờ (409 `queue_limit_reached`)."""
