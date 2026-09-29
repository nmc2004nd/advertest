"""Dependency xác thực người dùng: `current_user` đọc phiên, user, trạng thái và role từ DB ở
mọi request (requirements.md Phase 4: vô hiệu hóa, đổi role có hiệu lực ngay).

Cookie đọc từ `Request` (không khai tham số Cookie) để OpenAPI chỉ có security scheme
`userSession` của router.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request, status

from advertest_contracts.enums import ErrorCode, Role, UserStatus
from advertest_contracts.models import Me
from advertest_contracts.permissions import Permission, permissions_for
from backend.app.api.deps import SessionFactory, get_clock, get_sessionmaker, transaction
from backend.app.api.errors import ApiError
from backend.app.api.security import SESSION_COOKIE
from backend.app.auth import sessions
from backend.app.auth.service import load_roles
from backend.app.services.clock import Clock


@dataclass(frozen=True)
class Principal:
    """Người dùng đã xác thực của request hiện tại (bản sao, không gắn với session ORM)."""

    user_id: UUID
    session_id: UUID
    email: str
    full_name: str
    status: UserStatus
    roles: frozenset[Role]

    @property
    def permissions(self) -> frozenset[Permission]:
        return permissions_for(self.roles)

    def to_me(self) -> Me:
        return Me(
            id=self.user_id,
            full_name=self.full_name,
            email=self.email,
            roles=sorted(self.roles),
            permissions=sorted(self.permissions),
            status=self.status,
        )


def unauthenticated() -> ApiError:
    return ApiError(
        status.HTTP_401_UNAUTHORIZED, ErrorCode.UNAUTHENTICATED, "Chưa đăng nhập hoặc phiên đã hết"
    )


def current_user(
    request: Request,
    factory: Annotated[SessionFactory, Depends(get_sessionmaker)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> Principal:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise unauthenticated()
    with transaction(factory) as session:
        found = sessions.lookup(session, token, now=clock())
        if found is None:
            raise unauthenticated()
        row, user = found
        roles = load_roles(session, user.id)
        return Principal(
            user_id=user.id,
            session_id=row.id,
            email=user.email,
            full_name=user.full_name,
            status=user.status,
            roles=roles,
        )


CurrentUser = Annotated[Principal, Depends(current_user)]
