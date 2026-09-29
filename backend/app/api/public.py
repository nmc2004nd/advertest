"""Endpoint cho người dùng: mỗi nhóm một endpoint đại diện (khung tối thiểu), cộng đủ endpoint
xác thực, quản trị người dùng và audit log của Phase 4 (khung, trả 501 cho tới Group 1-3).

Model request/response chỉ dùng schema đã có trong `advertest_contracts`; schema còn lại
do phase tương ứng thêm vào contract (Phase 6-8). Phase 5 Group 0 thêm khung cho các endpoint
đọc tài nguyên, experiment, run, failure case và ảnh (requirements.md Phase 5, Behaviour).

Mọi route cần phiên khai quyền bằng `**guard(p)` (requirements.md Phase 4, mục Bảo vệ endpoint):
dependency kiểm tra phiên và permission chạy trước thân hàm (nên trước cả `501`), và `x-permission`
trong OpenAPI là một `Permission` của ma trận hoặc `authenticated` (chỉ cần đăng nhập).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, Security, status

from advertest_contracts.enums import ErrorCode, ExperimentStatus, UserStatus
from advertest_contracts.models import (
    AccessRequest,
    ApproveRequest,
    AttackSpec,
    AuditLogPage,
    ClassMappingSummary,
    ComputeTargetPublic,
    DatasetSummary,
    DatasetVersionSummary,
    ErrorResponse,
    EstimateResponse,
    ExperimentClone,
    ExperimentCreate,
    ExperimentDetail,
    ExperimentPage,
    FailureCaseView,
    LoginRequest,
    Manifest,
    Me,
    ModelSummary,
    PasswordChange,
    PasswordResetConsume,
    PasswordResetLink,
    ProtocolBody,
    ProtocolSummary,
    RejectRequest,
    RolesUpdate,
    RunView,
    SliceSummary,
    UserAdminPage,
    UserAdminView,
)
from advertest_contracts.permissions import AUTHENTICATED
from advertest_contracts.permissions import Permission as P
from backend.app.admin import users as admin_users
from backend.app.api.deps import SessionFactory, get_clock, get_sessionmaker, transaction
from backend.app.api.errors import (
    AUTH_REQUIRED_RESPONSES,
    NOT_IMPLEMENTED_RESPONSE,
    VALIDATION_ERROR_RESPONSE,
    ApiError,
    not_implemented,
)
from backend.app.api.security import user_session
from backend.app.audit.query import AuditFilter, list_entries
from backend.app.auth import service as auth_service
from backend.app.auth import sessions
from backend.app.auth.deps import CurrentUser
from backend.app.auth.permissions import guard
from backend.app.services import catalog
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
auth_public_router = APIRouter(
    prefix="/auth", tags=["auth"], responses=NOT_IMPLEMENTED_RESPONSE | VALIDATION_ERROR_RESPONSE
)


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
    responses=NOT_IMPLEMENTED_RESPONSE | AUTH_REQUIRED_RESPONSES | VALIDATION_ERROR_RESPONSE,
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
    factory: Sessions,
    status: UserStatus | None = None,
    cursor: Cursor = None,
    limit: Limit = 50,
) -> UserAdminPage:
    with transaction(factory) as session:
        return admin_users.list_users(session, status=status, cursor=cursor, limit=limit)


@router.post("/admin/users/{user_id}/approve", tags=["admin-users"], **guard(P.USER_MANAGE))
def approve_user(
    user_id: UUID, body: ApproveRequest, user: CurrentUser, factory: Sessions, clock: Now
) -> UserAdminView:
    with transaction(factory) as session:
        actor = admin_users.get_actor(session, user.user_id)
        return admin_users.approve(session, actor, user_id, list(body.roles), now=clock())


@router.post("/admin/users/{user_id}/reject", tags=["admin-users"], **guard(P.USER_MANAGE))
def reject_user(
    user_id: UUID, body: RejectRequest, user: CurrentUser, factory: Sessions
) -> UserAdminView:
    with transaction(factory) as session:
        actor = admin_users.get_actor(session, user.user_id)
        return admin_users.reject(session, actor, user_id, body.reason)


@router.put("/admin/users/{user_id}/roles", tags=["admin-users"], **guard(P.USER_MANAGE))
def update_user_roles(
    user_id: UUID, body: RolesUpdate, user: CurrentUser, factory: Sessions
) -> UserAdminView:
    with transaction(factory) as session:
        actor = admin_users.get_actor(session, user.user_id)
        return admin_users.update_roles(session, actor, user_id, list(body.roles))


@router.post("/admin/users/{user_id}/disable", tags=["admin-users"], **guard(P.USER_MANAGE))
def disable_user(user_id: UUID, user: CurrentUser, factory: Sessions, clock: Now) -> UserAdminView:
    with transaction(factory) as session:
        actor = admin_users.get_actor(session, user.user_id)
        return admin_users.disable(session, actor, user_id, now=clock())


@router.post("/admin/users/{user_id}/enable", tags=["admin-users"], **guard(P.USER_MANAGE))
def enable_user(user_id: UUID, user: CurrentUser, factory: Sessions) -> UserAdminView:
    with transaction(factory) as session:
        actor = admin_users.get_actor(session, user.user_id)
        return admin_users.enable(session, actor, user_id)


@router.post(
    "/admin/users/{user_id}/reset-link",
    tags=["admin-users"],
    **guard(P.USER_MANAGE),
)
def create_reset_link(
    user_id: UUID, user: CurrentUser, factory: Sessions, clock: Now
) -> PasswordResetLink:
    with transaction(factory) as session:
        actor = admin_users.get_actor(session, user.user_id)
        return admin_users.create_reset_link(session, actor, user_id, now=clock())


# ---------------------------------------------------------------- Phase 5: đọc tài nguyên

NOT_FOUND_RESPONSE: dict[int | str, dict[str, Any]] = {
    status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Không tồn tại"}
}


@router.get("/models", tags=["models"], **guard(P.MODEL_READ))
def list_models(factory: Sessions) -> list[ModelSummary]:
    with transaction(factory) as session:
        return catalog.list_models(session)


@router.get(
    "/models/{model_id}", tags=["models"], responses=NOT_FOUND_RESPONSE, **guard(P.MODEL_READ)
)
def get_model(model_id: UUID, factory: Sessions) -> ModelSummary:
    with transaction(factory) as session:
        return catalog.get_model(session, model_id)


@router.get("/datasets", tags=["datasets"], **guard(P.DATASET_READ))
def list_datasets(factory: Sessions) -> list[DatasetSummary]:
    with transaction(factory) as session:
        return catalog.list_datasets(session)


@router.get(
    "/dataset-versions/{dataset_version_id}",
    tags=["datasets"],
    responses=NOT_FOUND_RESPONSE,
    **guard(P.DATASET_READ),
)
def get_dataset_version(dataset_version_id: UUID, factory: Sessions) -> DatasetVersionSummary:
    with transaction(factory) as session:
        return catalog.get_dataset_version(session, dataset_version_id)


@router.get("/slices", tags=["slices"], **guard(P.DATASET_READ))
def list_slices(factory: Sessions, dataset_version: UUID | None = None) -> list[SliceSummary]:
    with transaction(factory) as session:
        return catalog.list_slices(session, dataset_version)


@router.get("/class-mappings", tags=["datasets"], **guard(P.DATASET_READ))
def list_class_mappings(
    factory: Sessions, dataset_version: UUID | None = None, model: UUID | None = None
) -> list[ClassMappingSummary]:
    with transaction(factory) as session:
        return catalog.list_class_mappings(session, dataset_version, model)


@router.get("/attack-specs", tags=["attack-specs"], **guard(P.ATTACK_CATALOG_READ))
def list_attack_specs(factory: Sessions) -> list[AttackSpec]:
    """Chỉ spec đang hoạt động."""
    with transaction(factory) as session:
        return catalog.list_attack_specs(session)


@router.get("/protocols", tags=["protocols"], **guard(P.PROTOCOL_READ))
def list_protocols(factory: Sessions) -> list[ProtocolSummary]:
    """Protocol trạng thái `active` và `dev`."""
    with transaction(factory) as session:
        return catalog.list_protocols(session)


@router.post("/protocols", tags=["protocols"], **guard(P.PROTOCOL_MANAGE))
def create_protocol(body: ProtocolBody) -> None:
    not_implemented()


@router.get("/compute-targets", tags=["compute-targets"], **guard(P.COMPUTE_TARGET_READ))
def list_compute_targets(factory: Sessions, clock: Now) -> list[ComputeTargetPublic]:
    """`online`: heartbeat trong 60 giây gần nhất; `queue_length`: số experiment `queued`."""
    with transaction(factory) as session:
        return catalog.list_compute_targets(session, clock())


# ---------------------------------------------------------------- Phase 5: experiment

CONFLICT_RESPONSE: dict[int | str, dict[str, Any]] = {
    status.HTTP_409_CONFLICT: {"model": ErrorResponse, "description": "Sai trạng thái"}
}


@router.get("/experiments", tags=["experiments"], **guard(P.EXPERIMENT_READ))
def list_experiments(
    owner: Literal["me", "all"] = "all",
    status: ExperimentStatus | None = None,
    model: UUID | None = None,
    cursor: Cursor = None,
    limit: Limit = 50,
) -> ExperimentPage:
    not_implemented()


@router.post(
    "/experiments",
    tags=["experiments"],
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_409_CONFLICT: {"model": ErrorResponse, "description": "queue_limit_reached"}
    },
    **guard(P.EXPERIMENT_CREATE),
)
def create_experiment(body: ExperimentCreate) -> ExperimentDetail:
    not_implemented()


@router.post("/experiments/estimate", tags=["experiments"], **guard(P.EXPERIMENT_CREATE))
def estimate_experiment(body: ExperimentCreate) -> EstimateResponse:
    """Kiểm tra cấu hình như khi tạo; không tạo gì."""
    not_implemented()


@router.get(
    "/experiments/{experiment_id}",
    tags=["experiments"],
    responses=NOT_FOUND_RESPONSE,
    **guard(P.EXPERIMENT_READ),
)
def get_experiment(experiment_id: UUID) -> ExperimentDetail:
    not_implemented()


@router.get(
    "/experiments/{experiment_id}/runs",
    tags=["experiments"],
    responses=NOT_FOUND_RESPONSE,
    **guard(P.EXPERIMENT_READ),
)
def list_experiment_runs(experiment_id: UUID) -> list[RunView]:
    not_implemented()


@router.post(
    "/experiments/{experiment_id}/cancel",
    tags=["experiments"],
    responses=NOT_FOUND_RESPONSE | CONFLICT_RESPONSE,
    **guard(P.EXPERIMENT_CANCEL_OWN),
)
def cancel_experiment(experiment_id: UUID) -> ExperimentDetail:
    """Chỉ chủ sở hữu (kiểm tra ở service); trạng thái `queued` hoặc `running`."""
    not_implemented()


@router.get(
    "/experiments/{experiment_id}/clone",
    tags=["experiments"],
    responses=NOT_FOUND_RESPONSE,
    **guard(P.EXPERIMENT_CREATE),
)
def clone_experiment(experiment_id: UUID) -> ExperimentClone:
    not_implemented()


@router.get(
    "/runs/{run_id}", tags=["runs"], responses=NOT_FOUND_RESPONSE, **guard(P.EXPERIMENT_READ)
)
def get_run(run_id: UUID) -> RunView:
    not_implemented()


@router.get(
    "/runs/{run_id}/manifest",
    tags=["runs"],
    responses=NOT_FOUND_RESPONSE,
    **guard(P.EXPERIMENT_READ),
)
def get_run_manifest(run_id: UUID) -> Manifest:
    not_implemented()


@router.get(
    "/runs/{run_id}/failure-cases",
    tags=["runs"],
    responses=NOT_FOUND_RESPONSE,
    **guard(P.EXPERIMENT_READ),
)
def list_run_failure_cases(run_id: UUID) -> list[FailureCaseView]:
    """Sắp theo `severity_score` giảm dần; chỉ có URL thumbnail."""
    not_implemented()


@router.get(
    "/failure-cases/{case_id}",
    tags=["failure-cases"],
    responses=NOT_FOUND_RESPONSE,
    **guard(P.EXPERIMENT_READ),
)
def get_failure_case(case_id: UUID) -> FailureCaseView:
    not_implemented()


@router.get(
    "/artifacts/{token}",
    tags=["artifacts"],
    response_class=Response,
    responses={
        status.HTTP_200_OK: {
            "content": {"image/png": {}, "image/webp": {}},
            "description": "Ảnh của đúng đối tượng gắn với token",
        },
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "Token sai, bị sửa hoặc hết hạn (10 phút)",
        },
    },
    **guard(P.EXPERIMENT_READ),
)
def get_artifact(token: str) -> Response:
    """Stream ảnh từ MinIO. Cần cả phiên có `experiment.read` lẫn token do API cấp trong
    `FailureCaseView.urls`."""
    not_implemented()


@router.get("/reviews", tags=["reviews"], **guard(P.REVIEW_DECIDE))
def list_reviews() -> None:
    not_implemented()


@router.get("/reports/{report_id}", tags=["reports"], **guard(P.REPORT_READ))
def get_report(report_id: UUID) -> None:
    not_implemented()


@router.get("/budget", tags=["budget"], **guard(P.BUDGET_MANAGE))
def get_budget() -> None:
    not_implemented()


@router.get("/audit-log", tags=["audit-log"], **guard(P.AUDIT_READ))
def list_audit_log(
    factory: Sessions,
    actor_id: UUID | None = None,
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: UUID | None = None,
    since: Annotated[datetime | None, Query(description="Từ thời điểm (UTC, gồm)")] = None,
    until: Annotated[datetime | None, Query(description="Tới thời điểm (UTC, không gồm)")] = None,
    cursor: Cursor = None,
    limit: Limit = 50,
) -> AuditLogPage:
    filters = AuditFilter(actor_id, action, entity_type, entity_id, since, until)
    with transaction(factory) as session:
        return list_entries(session, filters, cursor=cursor, limit=limit)


# Trang xác minh report công khai, không cần đăng nhập.
verify_router = APIRouter(responses=NOT_IMPLEMENTED_RESPONSE | VALIDATION_ERROR_RESPONSE)


@verify_router.get("/verify/{report_id}", tags=["verify"])
def verify_report(report_id: UUID) -> None:
    not_implemented()
