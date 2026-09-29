"""Endpoint cho người dùng: mỗi nhóm một endpoint đại diện (khung tối thiểu), cộng đủ endpoint
xác thực, quản trị người dùng và audit log của Phase 4 (khung, trả 501 cho tới Group 1-3).

Model request/response chỉ dùng schema đã có trong `advertest_contracts`; schema còn lại
do phase tương ứng thêm vào contract (Phase 5-8).

Mọi route cần phiên khai `x-permission` trong OpenAPI (requirements.md Phase 4, mục Bảo vệ
endpoint): một `Permission` trong ma trận, hoặc `authenticated` với route chỉ cần đăng nhập.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query, Security, status

from advertest_contracts.enums import UserStatus
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
from advertest_contracts.permissions import AUTHENTICATED, PermissionRequirement
from advertest_contracts.permissions import Permission as P
from backend.app.api.errors import (
    AUTH_REQUIRED_RESPONSES,
    NOT_IMPLEMENTED_RESPONSE,
    not_implemented,
)
from backend.app.api.security import user_session


def permission(required: PermissionRequirement) -> dict[str, Any]:
    """`openapi_extra` khai báo permission của route (extension `x-permission`)."""
    return {"x-permission": str(required)}


# Endpoint công khai của xác thực: không cần phiên.
auth_public_router = APIRouter(prefix="/auth", tags=["auth"], responses=NOT_IMPLEMENTED_RESPONSE)


@auth_public_router.post("/request-access", status_code=status.HTTP_202_ACCEPTED)
def request_access(body: AccessRequest) -> None:
    not_implemented()


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
def login(body: LoginRequest) -> Me:
    not_implemented()


@auth_public_router.post("/password-reset", status_code=status.HTTP_204_NO_CONTENT)
def consume_password_reset(body: PasswordResetConsume) -> None:
    not_implemented()


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
    openapi_extra=permission(AUTHENTICATED),
)
def logout() -> None:
    not_implemented()


@router.get("/auth/me", tags=["auth"], openapi_extra=permission(AUTHENTICATED))
def get_me() -> Me:
    not_implemented()


@router.post(
    "/auth/password",
    tags=["auth"],
    status_code=status.HTTP_204_NO_CONTENT,
    openapi_extra=permission(AUTHENTICATED),
)
def change_password(body: PasswordChange) -> None:
    not_implemented()


@router.get("/admin/users", tags=["admin-users"], openapi_extra=permission(P.USER_MANAGE))
def list_users(
    status: UserStatus | None = None, cursor: Cursor = None, limit: Limit = 50
) -> UserAdminPage:
    not_implemented()


@router.post(
    "/admin/users/{user_id}/approve", tags=["admin-users"], openapi_extra=permission(P.USER_MANAGE)
)
def approve_user(user_id: UUID, body: ApproveRequest) -> UserAdminView:
    not_implemented()


@router.post(
    "/admin/users/{user_id}/reject", tags=["admin-users"], openapi_extra=permission(P.USER_MANAGE)
)
def reject_user(user_id: UUID, body: RejectRequest) -> UserAdminView:
    not_implemented()


@router.put(
    "/admin/users/{user_id}/roles", tags=["admin-users"], openapi_extra=permission(P.USER_MANAGE)
)
def update_user_roles(user_id: UUID, body: RolesUpdate) -> UserAdminView:
    not_implemented()


@router.post(
    "/admin/users/{user_id}/disable", tags=["admin-users"], openapi_extra=permission(P.USER_MANAGE)
)
def disable_user(user_id: UUID) -> UserAdminView:
    not_implemented()


@router.post(
    "/admin/users/{user_id}/enable", tags=["admin-users"], openapi_extra=permission(P.USER_MANAGE)
)
def enable_user(user_id: UUID) -> UserAdminView:
    not_implemented()


@router.post(
    "/admin/users/{user_id}/reset-link",
    tags=["admin-users"],
    openapi_extra=permission(P.USER_MANAGE),
)
def create_reset_link(user_id: UUID) -> PasswordResetLink:
    not_implemented()


@router.get("/models", tags=["models"], openapi_extra=permission(P.MODEL_READ))
def list_models() -> None:
    not_implemented()


@router.get("/datasets", tags=["datasets"], openapi_extra=permission(P.DATASET_READ))
def list_datasets() -> None:
    not_implemented()


@router.get("/slices", tags=["slices"], openapi_extra=permission(P.DATASET_READ))
def list_slices() -> None:
    not_implemented()


@router.get("/attack-specs", tags=["attack-specs"], openapi_extra=permission(P.ATTACK_CATALOG_READ))
def list_attack_specs() -> list[AttackSpec]:
    not_implemented()


@router.post("/protocols", tags=["protocols"], openapi_extra=permission(P.PROTOCOL_MANAGE))
def create_protocol(body: ProtocolBody) -> None:
    not_implemented()


@router.post("/experiments", tags=["experiments"], openapi_extra=permission(P.EXPERIMENT_CREATE))
def create_experiment(config: ExperimentConfig) -> None:
    not_implemented()


@router.get("/runs/{run_id}", tags=["runs"], openapi_extra=permission(P.EXPERIMENT_READ))
def get_run(run_id: UUID) -> RunResult:
    not_implemented()


@router.get(
    "/failure-cases/{case_id}", tags=["failure-cases"], openapi_extra=permission(P.EXPERIMENT_READ)
)
def get_failure_case(case_id: UUID) -> None:
    not_implemented()


@router.get("/reviews", tags=["reviews"], openapi_extra=permission(P.REVIEW_DECIDE))
def list_reviews() -> None:
    not_implemented()


@router.get("/reports/{report_id}", tags=["reports"], openapi_extra=permission(P.REPORT_READ))
def get_report(report_id: UUID) -> None:
    not_implemented()


@router.get(
    "/compute-targets", tags=["compute-targets"], openapi_extra=permission(P.COMPUTE_TARGET_READ)
)
def list_compute_targets() -> None:
    not_implemented()


@router.get("/budget", tags=["budget"], openapi_extra=permission(P.BUDGET_MANAGE))
def get_budget() -> None:
    not_implemented()


@router.get("/audit-log", tags=["audit-log"], openapi_extra=permission(P.AUDIT_READ))
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
