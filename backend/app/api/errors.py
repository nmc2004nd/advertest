"""Lỗi dùng chung của API: mọi lỗi trả body `ErrorResponse` {"error": {"code", "message"}}."""

from __future__ import annotations

from typing import Any, NoReturn

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from advertest_contracts.enums import ErrorCode
from advertest_contracts.models import ErrorBody, ErrorResponse
from backend.app.services.errors import Conflict, Forbidden, Invalid, NotFound, ServiceError


class ApiError(Exception):
    def __init__(self, status_code: int, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def not_implemented() -> NoReturn:
    raise ApiError(
        status.HTTP_501_NOT_IMPLEMENTED,
        ErrorCode.NOT_IMPLEMENTED,
        "Endpoint chưa được cài đặt.",
    )


# Khai báo trong OpenAPI cho mọi endpoint khung (truyền vào `responses=` của router).
NOT_IMPLEMENTED_RESPONSE: dict[int | str, dict[str, Any]] = {
    status.HTTP_501_NOT_IMPLEMENTED: {"model": ErrorResponse, "description": "Chưa cài đặt"}
}


# Khai báo trong OpenAPI cho mọi route cần phiên người dùng (Phase 4).
AUTH_REQUIRED_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse, "description": "Thiếu phiên hợp lệ"},
    status.HTTP_403_FORBIDDEN: {"model": ErrorResponse, "description": "Thiếu permission"},
}


# Lỗi nghiệp vụ của service (backend/app/services/errors.py) → HTTP.
SERVICE_ERRORS: dict[type[ServiceError], tuple[int, ErrorCode]] = {
    NotFound: (status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND),
    Forbidden: (status.HTTP_403_FORBIDDEN, ErrorCode.FORBIDDEN),
    Conflict: (status.HTTP_409_CONFLICT, ErrorCode.CONFLICT),
    Invalid: (status.HTTP_422_UNPROCESSABLE_CONTENT, ErrorCode.INVALID_REQUEST),
}


def _error(status_code: int, code: ErrorCode, message: str) -> JSONResponse:
    body = ErrorResponse(error=ErrorBody(code=code, message=message))
    return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return _error(exc.status_code, exc.code, exc.message)

    @app.exception_handler(ServiceError)
    async def _service_error(_: Request, exc: ServiceError) -> JSONResponse:
        status_code, code = next(
            mapping for cls, mapping in SERVICE_ERRORS.items() if isinstance(exc, cls)
        )
        return _error(status_code, code, str(exc))
