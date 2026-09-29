"""Lỗi nghiệp vụ. Tầng API (Group 3) đổi sang HTTP: NotFound → 404, Forbidden → 403,
Conflict → 409, Invalid → 422."""

from __future__ import annotations


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
