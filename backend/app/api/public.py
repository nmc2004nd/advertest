"""Endpoint cho người dùng: mỗi nhóm một endpoint đại diện (khung tối thiểu), cộng đủ endpoint
xác thực, quản trị người dùng và audit log của Phase 4 (khung, trả 501 cho tới Group 1-3).

Model request/response chỉ dùng schema đã có trong `advertest_contracts`; schema còn lại
do phase tương ứng thêm vào contract (Phase 5-8).

Mọi route cần phiên khai quyền bằng `**guard(p)` (requirements.md Phase 4, mục Bảo vệ endpoint):
dependency kiểm tra phiên và permission chạy trước thân hàm (nên trước cả `501`), và `x-permission`
trong OpenAPI là một `Permission` của ma trận hoặc `authenticated` (chỉ cần đăng nhập).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, Security, status

from advertest_contracts.enums import ErrorCode, UserStatus
from advertest_contracts.models import (
    AccessRequest,
    ApproveRequest,
    AttackSpec,
    AuditLogPage,
    ErrorResponse,
    ExperimentConfig,
    LoginRequest,
    Me,
    PasswordChange,
    PasswordResetConsume,
    PasswordResetLink,
    ProtocolBody,
    RejectRequest,
    RolesUpdate,
    RunResult,
    UserAdminPage,
    UserAdminView,
)
from advertest_contracts.permissions import AUTHENTICATED
from advertest_contracts.permissions import Permission as P
from backend.app.api.deps import SessionFactory, get_clock, get_sessionmaker, transaction
from backend.app.api.errors import (
    AUTH_REQUIRED_RESPONSES,
    NOT_IMPLEMENTED_RESPONSE,
    ApiError,
    not_implemented,
)
from backend.app.api.security import user_session
from backend.app.auth import service as auth_service
from backend.app.auth import sessions
from backend.app.auth.deps import CurrentUser
from backend.app.auth.permissions import guard
from backend.app.services.clock import Clock

Sessions = Annotated[SessionFactory, Depends(get_sessionmaker)]
Now = Annotated[Clock, Depends(get_clock)]

AUTH_FAILURE_STATUS = {
    ErrorCode.INVALID_CREDENTIALS: status.HTTP_401_UNAUTHORIZED,
    ErrorCode.ACCOUNT_PENDING: status.HTTP_403_FORBIDDEN,
    ErrorCode.ACCOUNT_REJECTED: status.HTTP_403_FORBIDDEN,
    ErrorCode.ACCOUNT_DISABLED: status.HTTP_403_FORBIDDEN,
    ErrorCode.RATE_LIMITED: status.HTTP_429_TOO_MANY_REQUESTS,
    ErrorCode.INVALID_REQUEST: status.HTTP_422_UNPROCESSABLE_CONTENT,
    ErrorCode.VALIDATION_ERROR: status.HTTP_422_UNPROCESSABLE_CONTENT,
}


def auth_error(failure: auth_service.AuthFailure) -> ApiError:
    return ApiError(AUTH_FAILURE_STATUS[failure.code], failure.code, failure.message)


def client_ip(request: Request) -> str | None:
    """IP đã qua ProxyHeadersMiddleware (X-Forwarded-For chỉ khi đến từ TRUSTED_PROXIES)."""
    return request.client.host if request.client else None


# Endpoint công khai của xác thực: không cần phiên.
auth_public_router = APIRouter(prefix="/auth", tags=["auth"], responses=NOT_IMPLEMENTED_RESPONSE)


@auth_public_router.post("/request-access", status_code=status.HTTP_202_ACCEPTED)
def request_access(body: AccessRequest, factory: Sessions) -> Response:
    with transaction(factory) as session:
        auth_service.request_access(session, body)
    # 202 không có body (requirements.md Phase 4), không phải JSON `null`.
    return Response(status_code=status.HTTP_202_ACCEPTED)


@auth_public_router.post(
    "/login",
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "model": ErrorResponse,
            "description": "invalid_credentials",
        },
        status.HTTP_403_FORBIDDEN: {
            "model": ErrorResponse,
            "description": "account_pending, account_rejected hoặc account_disabled",
        },
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse, "description": "rate_limited"},
    },
)
def login(
    body: LoginRequest, request: Request, response: Response, factory: Sessions, clock: Now
) -> Me:
    now = clock()
    with transaction(factory) as session:
        outcome = auth_service.login(
            session,
            body,
            ip=client_ip(request),
            user_agent=request.headers.get("user-agent"),
            now=now,
        )
    # Lỗi ném sau khi commit: sự kiện login_failed phải được ghi lại.
    if isinstance(outcome, auth_service.AuthFailure):
        raise auth_error(outcome)
    sessions.set_cookies(response, outcome.issued, now=now)
    return outcome.me


@auth_public_router.post("/password-reset", status_code=status.HTTP_204_NO_CONTENT)
def consume_password_reset(body: PasswordResetConsume, factory: Sessions, clock: Now) -> None:
    with transaction(factory) as session:
        failure = auth_service.consume_password_reset(session, body, now=clock())
        if failure is not None:
            raise auth_error(failure)


router = APIRouter(
    dependencies=[Security(user_session)],
    responses=NOT_IMPLEMENTED_RESPONSE | AUTH_REQUIRED_RESPONSES,
)

Cursor = Annotated[str | None, Query(description="next_cursor của trang trước")]
Limit = Annotated[int, Query(ge=1, le=100)]


@router.post(
    "/auth/logout",
    tags=["auth"],
    status_code=status.HTTP_204_NO_CONTENT,
    **guard(AUTHENTICATED),
)
def logout(
    user: CurrentUser, request: Request, response: Response, factory: Sessions, clock: Now
) -> None:
    with transaction(factory) as session:
        auth_service.logout(
            session,
            session_id=user.session_id,
            email=user.email,
            ip=client_ip(request),
            now=clock(),
        )
    sessions.clear_cookies(response)


@router.get("/auth/me", tags=["auth"], **guard(AUTHENTICATED))
def get_me(user: CurrentUser) -> Me:
    return user.to_me()


@router.post(
    "/auth/password",
    tags=["auth"],
    status_code=status.HTTP_204_NO_CONTENT,
    **guard(AUTHENTICATED),
)
def change_password(body: PasswordChange, user: CurrentUser, factory: Sessions, clock: Now) -> None:
    with transaction(factory) as session:
        failure = auth_service.change_password(
            session, user_id=user.user_id, session_id=user.session_id, body=body, now=clock()
        )
        if failure is not None:
            raise auth_error(failure)


@router.get("/admin/users", tags=["admin-users"], **guard(P.USER_MANAGE))
def list_users(
    status: UserStatus | None = None, cursor: Cursor = None, limit: Limit = 50
) -> UserAdminPage:
    not_implemented()


@router.post("/admin/users/{user_id}/approve", tags=["admin-users"], **guard(P.USER_MANAGE))
def approve_user(user_id: UUID, body: ApproveRequest) -> UserAdminView:
    not_implemented()


@router.post("/admin/users/{user_id}/reject", tags=["admin-users"], **guard(P.USER_MANAGE))
def reject_user(user_id: UUID, body: RejectRequest) -> UserAdminView:
    not_implemented()


@router.put("/admin/users/{user_id}/roles", tags=["admin-users"], **guard(P.USER_MANAGE))
def update_user_roles(user_id: UUID, body: RolesUpdate) -> UserAdminView:
    not_implemented()


@router.post("/admin/users/{user_id}/disable", tags=["admin-users"], **guard(P.USER_MANAGE))
def disable_user(user_id: UUID) -> UserAdminView:
    not_implemented()


@router.post("/admin/users/{user_id}/enable", tags=["admin-users"], **guard(P.USER_MANAGE))
def enable_user(user_id: UUID) -> UserAdminView:
    not_implemented()


@router.post(
    "/admin/users/{user_id}/reset-link",
    tags=["admin-users"],
    **guard(P.USER_MANAGE),
)
def create_reset_link(user_id: UUID) -> PasswordResetLink:
    not_implemented()


@router.get("/models", tags=["models"], **guard(P.MODEL_READ))
def list_models() -> None:
    not_implemented()


@router.get("/datasets", tags=["datasets"], **guard(P.DATASET_READ))
def list_datasets() -> None:
    not_implemented()


@router.get("/slices", tags=["slices"], **guard(P.DATASET_READ))
def list_slices() -> None:
    not_implemented()


@router.get("/attack-specs", tags=["attack-specs"], **guard(P.ATTACK_CATALOG_READ))
def list_attack_specs() -> list[AttackSpec]:
    not_implemented()


@router.post("/protocols", tags=["protocols"], **guard(P.PROTOCOL_MANAGE))
def create_protocol(body: ProtocolBody) -> None:
    not_implemented()


@router.post("/experiments", tags=["experiments"], **guard(P.EXPERIMENT_CREATE))
def create_experiment(config: ExperimentConfig) -> None:
    not_implemented()


@router.get("/runs/{run_id}", tags=["runs"], **guard(P.EXPERIMENT_READ))
def get_run(run_id: UUID) -> RunResult:
    not_implemented()


@router.get("/failure-cases/{case_id}", tags=["failure-cases"], **guard(P.EXPERIMENT_READ))
def get_failure_case(case_id: UUID) -> None:
    not_implemented()


@router.get("/reviews", tags=["reviews"], **guard(P.REVIEW_DECIDE))
def list_reviews() -> None:
    not_implemented()


@router.get("/reports/{report_id}", tags=["reports"], **guard(P.REPORT_READ))
def get_report(report_id: UUID) -> None:
    not_implemented()


@router.get("/compute-targets", tags=["compute-targets"], **guard(P.COMPUTE_TARGET_READ))
def list_compute_targets() -> None:
    not_implemented()


@router.get("/budget", tags=["budget"], **guard(P.BUDGET_MANAGE))
def get_budget() -> None:
    not_implemented()


@router.get("/audit-log", tags=["audit-log"], **guard(P.AUDIT_READ))
def list_audit_log(
    actor_id: UUID | None = None,
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: UUID | None = None,
    since: Annotated[datetime | None, Query(description="Từ thời điểm (UTC, gồm)")] = None,
    until: Annotated[datetime | None, Query(description="Tới thời điểm (UTC, không gồm)")] = None,
    cursor: Cursor = None,
    limit: Limit = 50,
) -> AuditLogPage:
    not_implemented()


# Trang xác minh report công khai, không cần đăng nhập.
verify_router = APIRouter(responses=NOT_IMPLEMENTED_RESPONSE)


@verify_router.get("/verify/{report_id}", tags=["verify"])
def verify_report(report_id: UUID) -> None:
    not_implemented()
