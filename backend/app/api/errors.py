"""Lỗi dùng chung của API: mọi lỗi trả body `ErrorResponse` {"error": {"code", "message"}}."""

from __future__ import annotations

from typing import Any, NoReturn

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from advertest_contracts.enums import ErrorCode
from advertest_contracts.models import ErrorBody, ErrorResponse


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


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        body = ErrorResponse(error=ErrorBody(code=exc.code, message=exc.message))
        return JSONResponse(status_code=exc.status_code, content=body.model_dump(mode="json"))
