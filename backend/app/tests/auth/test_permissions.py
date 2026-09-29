"""`require_permission` theo ma trận quyền (validation.md Phase 4, test_route_protection)."""

from __future__ import annotations

import uuid

import pytest

from advertest_contracts.enums import Role, UserStatus
from advertest_contracts.permissions import AUTHENTICATED, ROLE_PERMISSIONS, Permission
from backend.app.api.errors import ApiError
from backend.app.auth.deps import Principal
from backend.app.auth.permissions import guard, require_permission


def principal(*roles: Role) -> Principal:
    return Principal(
        user_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        email="u@x.test",
        full_name="U",
        status=UserStatus.ACTIVE,
        roles=frozenset(roles),
    )


@pytest.mark.parametrize("role", list(Role))
@pytest.mark.parametrize("permission", list(Permission))
def test_single_role_is_allowed_iff_matrix_says_so(role: Role, permission: Permission) -> None:
    check = require_permission(permission)
    user = principal(role)
    if permission in ROLE_PERMISSIONS[role]:
        assert check(user) is user
    else:
        with pytest.raises(ApiError) as caught:
            check(user)
        assert (caught.value.status_code, caught.value.code) == (403, "forbidden")


def test_multiple_roles_get_the_union() -> None:
    user = principal(Role.ENGINEER, Role.REVIEWER)
    require_permission(Permission.EXPERIMENT_CREATE)(user)
    require_permission(Permission.REVIEW_DECIDE)(user)
    with pytest.raises(ApiError):
        require_permission(Permission.USER_MANAGE)(user)


def test_authenticated_only_needs_a_session() -> None:
    user = principal()
    assert require_permission(AUTHENTICATED)(user) is user


def test_guard_keeps_dependency_and_openapi_in_sync() -> None:
    declared = guard(Permission.MODEL_READ)
    assert declared["openapi_extra"] == {"x-permission": "model.read"}
    [dependency] = declared["dependencies"]
    assert dependency.dependency.requirement == Permission.MODEL_READ
