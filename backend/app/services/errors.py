"""Lỗi nghiệp vụ. Tầng API đổi sang HTTP: NotFound → 404, Forbidden → 403, Conflict → 409,
Invalid → 422; `InvalidConfig` và `QueueLimitReached` mang mã lỗi riêng (Phase 5)."""

from __future__ import annotations

from collections.abc import Sequence

from advertest_contracts.enums import ErrorCode
from advertest_contracts.models import ComplianceItem, FieldError


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
    `not_supported_yet` khi có tính năng chưa hỗ trợ (mode = search), `not_compliant` khi cấu
    hình hợp lệ nhưng không tuân thủ protocol (Phase 8, kèm `compliance`), ngược lại
    `invalid_request`."""

    def __init__(
        self,
        message: str,
        fields: Sequence[FieldError],
        code: ErrorCode,
        compliance: Sequence[ComplianceItem] | None = None,
    ) -> None:
        super().__init__(message)
        self.fields = list(fields)
        self.code = code
        # Phase 8: có khi code = not_compliant (mọi mục, kể cả mục đã thỏa).
        self.compliance = list(compliance) if compliance is not None else None


class QueueLimitReached(Conflict):
    """Người dùng đã có đủ số experiment đang chờ (409 `queue_limit_reached`)."""
