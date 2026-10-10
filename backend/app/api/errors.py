"""Lỗi dùng chung của API: mọi lỗi trả body `ErrorResponse` {"error": {"code", "message"}}."""

from __future__ import annotations

import logging
from typing import Any, NoReturn

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from advertest_contracts.enums import ErrorCode
from advertest_contracts.models import (
    ChecklistItem,
    ComplianceItem,
    ErrorBody,
    ErrorResponse,
    FieldError,
)
from backend.app.services.errors import (
    ChecklistIncomplete,
    Conflict,
    ExperimentLocked,
    Forbidden,
    Gone,
    Invalid,
    InvalidConfig,
    NotFound,
    QueueLimitReached,
    QuickTryBusy,
    ServiceError,
)

logger = logging.getLogger(__name__)


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: ErrorCode,
        message: str,
        fields: list[FieldError] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.fields = fields


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


# Khai báo trong OpenAPI cho route có tham số hoặc body (Phase 5, plan.md task 1a): thay
# `HTTPValidationError` mặc định của FastAPI, vì mọi lỗi 422 đều trả `ErrorResponse`.
VALIDATION_ERROR_RESPONSE: dict[int | str, dict[str, Any]] = {
    status.HTTP_422_UNPROCESSABLE_CONTENT: {
        "model": ErrorResponse,
        "description": "validation_error (sai schema) hoặc invalid_request (sai nghiệp vụ)",
    }
}


# Lỗi nghiệp vụ của service (backend/app/services/errors.py) → HTTP.
SERVICE_ERRORS: dict[type[ServiceError], tuple[int, ErrorCode]] = {
    NotFound: (status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND),
    Forbidden: (status.HTTP_403_FORBIDDEN, ErrorCode.FORBIDDEN),
    Conflict: (status.HTTP_409_CONFLICT, ErrorCode.CONFLICT),
    Invalid: (status.HTTP_422_UNPROCESSABLE_CONTENT, ErrorCode.INVALID_REQUEST),
    Gone: (status.HTTP_410_GONE, ErrorCode.GONE),
    QuickTryBusy: (status.HTTP_429_TOO_MANY_REQUESTS, ErrorCode.QUICK_TRY_BUSY),
}


def error_response(
    status_code: int,
    code: ErrorCode,
    message: str,
    fields: list[FieldError] | None = None,
    *,
    compliance: list[ComplianceItem] | None = None,
    checklist: list[ChecklistItem] | None = None,
) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorBody(
            code=code, message=message, fields=fields, compliance=compliance, checklist=checklist
        )
    )
    # `fields` chỉ xuất hiện khi có: body lỗi cũ giữ nguyên {"code", "message"}.
    return JSONResponse(
        status_code=status_code, content=body.model_dump(mode="json", exclude_none=True)
    )


# Lỗi HTTP của framework (route không tồn tại, sai method...) → ErrorCode theo status.
HTTP_STATUS_CODES: dict[int, ErrorCode] = {
    status.HTTP_401_UNAUTHORIZED: ErrorCode.UNAUTHENTICATED,
    status.HTTP_403_FORBIDDEN: ErrorCode.FORBIDDEN,
    status.HTTP_404_NOT_FOUND: ErrorCode.NOT_FOUND,
    status.HTTP_409_CONFLICT: ErrorCode.CONFLICT,
    status.HTTP_501_NOT_IMPLEMENTED: ErrorCode.NOT_IMPLEMENTED,
}


def _loc(error: Any) -> str:
    return ".".join(str(part) for part in error.get("loc", ()) if part != "body")


def validation_fields(exc: RequestValidationError) -> list[FieldError] | None:
    """Đường dẫn từng trường sai (Phase 5: giao diện hiển thị lỗi tại đúng trường)."""
    fields = [
        FieldError(
            path=_loc(error) or "body",
            message=str(error.get("msg", "không hợp lệ")).removeprefix("Value error, "),
        )
        for error in exc.errors()
    ]
    return fields or None


def validation_message(exc: RequestValidationError) -> str:
    """Thông điệp từ lỗi đầu tiên: đường dẫn trường và mô tả. Không lặp lại giá trị gửi lên
    (có thể là mật khẩu)."""
    errors = exc.errors()
    if not errors:
        return "Dữ liệu gửi lên không hợp lệ"
    first = errors[0]
    loc = _loc(first)
    message = str(first.get("msg", "không hợp lệ")).removeprefix("Value error, ")
    more = f" (và {len(errors) - 1} lỗi khác)" if len(errors) > 1 else ""
    return f"{loc}: {message}{more}" if loc else f"{message}{more}"


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Body sai schema: 422 `validation_error` thay body mặc định {"detail": ...} của FastAPI.
        return error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            ErrorCode.VALIDATION_ERROR,
            validation_message(exc),
            validation_fields(exc),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = HTTP_STATUS_CODES.get(exc.status_code, ErrorCode.INVALID_REQUEST)
        response = error_response(exc.status_code, code, str(exc.detail))
        for name, value in (exc.headers or {}).items():
            response.headers[name] = value
        return response

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return error_response(exc.status_code, exc.code, exc.message, exc.fields)

    @app.exception_handler(ServiceError)
    async def _service_error(_: Request, exc: ServiceError) -> JSONResponse:
        if isinstance(exc, InvalidConfig):
            return error_response(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                exc.code,
                str(exc),
                exc.fields or None,
                compliance=exc.compliance,
            )
        if isinstance(exc, ExperimentLocked):
            return error_response(status.HTTP_409_CONFLICT, ErrorCode.EXPERIMENT_LOCKED, str(exc))
        if isinstance(exc, ChecklistIncomplete):
            return error_response(
                status.HTTP_409_CONFLICT,
                ErrorCode.CHECKLIST_INCOMPLETE,
                str(exc),
                checklist=exc.checklist,
            )
        if isinstance(exc, QueueLimitReached):
            return error_response(status.HTTP_409_CONFLICT, ErrorCode.QUEUE_LIMIT_REACHED, str(exc))
        status_code, code = next(
            mapping for cls, mapping in SERVICE_ERRORS.items() if isinstance(exc, cls)
        )
        return error_response(status_code, code, str(exc))

    @app.exception_handler(Exception)
    async def _internal_error(_: Request, exc: Exception) -> JSONResponse:
        # Lỗi không lường trước: không trả chi tiết (host, SQL, stack trace), chỉ ghi log server.
        logger.exception("Lỗi không xử lý được", exc_info=exc)
        return error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            ErrorCode.INTERNAL_ERROR,
            "Máy chủ gặp lỗi. Vui lòng thử lại sau.",
        )
