"""Phân quyền theo ma trận `ROLE_PERMISSIONS` của contract (requirements.md Phase 4, mục Bảo vệ
endpoint).

Mỗi route cần phiên khai quyền bằng `**guard(p)`: một nguồn duy nhất cho dependency kiểm tra
thật (`require_permission`) và extension `x-permission` trong OpenAPI. `check_route_permissions`
từ chối app có route không công khai thiếu khai báo, hoặc khai báo lệch nhau.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, FastAPI, status
from fastapi.routing import APIRoute, RouteContext, iter_route_contexts

from advertest_contracts.enums import ErrorCode
from advertest_contracts.permissions import AUTHENTICATED, Permission, PermissionRequirement
from backend.app.api.errors import ApiError
from backend.app.auth.deps import Principal, current_user

# Route không cần phiên (requirements.md Phase 4). /internal/worker dùng token của compute target.
PUBLIC_PATHS = frozenset(
    {
        "/health",
        "/auth/request-access",
        "/auth/login",
        "/auth/password-reset",
        "/verify/{report_id}",
    }
)
WORKER_PREFIX = "/internal/worker"
X_PERMISSION = "x-permission"


class PermissionDependency:
    """Dependency `require_permission(p)`; giữ `requirement` để kiểm tra lúc khởi động."""

    def __init__(self, requirement: PermissionRequirement) -> None:
        self.requirement = requirement

    def __call__(self, user: Annotated[Principal, Depends(current_user)]) -> Principal:
        if self.requirement == AUTHENTICATED or Permission(self.requirement) in user.permissions:
            return user
        raise ApiError(
            status.HTTP_403_FORBIDDEN,
            ErrorCode.FORBIDDEN,
            f"Không có quyền {self.requirement}",
        )


def require_permission(requirement: PermissionRequirement) -> PermissionDependency:
    return PermissionDependency(requirement)


def guard(requirement: PermissionRequirement) -> dict[str, Any]:
    """Tham số cho decorator route: `@router.get(path, **guard(P.MODEL_READ))`."""
    return {
        "dependencies": [Depends(require_permission(requirement))],
        "openapi_extra": {X_PERMISSION: str(requirement)},
    }


def _declared(route: RouteContext) -> list[str]:
    return [
        str(dep.call.requirement)
        for dep in route.dependant.dependencies
        if isinstance(dep.call, PermissionDependency)
    ]


def route_permission_errors(app: FastAPI) -> list[str]:
    errors = []
    # FastAPI giữ router con dưới dạng tham chiếu (không chép route vào app.routes):
    # `iter_route_contexts` trả route thật với đường dẫn đầy đủ và dependency của cả router, như
    # khi sinh OpenAPI.
    for route in iter_route_contexts(app.routes):
        if not isinstance(route.original_route, APIRoute):
            continue
        path = route.path or ""
        if path in PUBLIC_PATHS or path.startswith(WORKER_PREFIX):
            continue
        declared = _declared(route)
        extra = (route.openapi_extra or {}).get(X_PERMISSION)
        methods = ",".join(sorted(route.methods or ()))
        if len(declared) != 1:
            errors.append(f"{methods} {path}: cần đúng một require_permission")
        elif extra != declared[0]:
            errors.append(
                f"{methods} {path}: x-permission {extra!r} khác dependency {declared[0]!r}"
            )
    return errors


def check_route_permissions(app: FastAPI) -> None:
    """Mọi route không công khai (trừ /internal/worker) phải khai quyền; thiếu thì không chạy."""
    errors = route_permission_errors(app)
    if errors:
        raise RuntimeError("Route thiếu hoặc sai khai báo permission:\n" + "\n".join(errors))
