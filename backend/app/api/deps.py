"""Dependency của API: transaction Postgres, storage MinIO, đồng hồ, xác thực worker.

Mỗi endpoint mở transaction bằng `transaction(...)` (commit khi xong, rollback khi lỗi) thay vì
dependency có `yield`, để commit luôn xảy ra trước khi trả response.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from functools import cache
from typing import Annotated

from fastapi import Security, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session, sessionmaker

from advertest_contracts.enums import ErrorCode
from backend.app.api.errors import ApiError
from backend.app.api.security import worker_token
from backend.app.db import models as m
from backend.app.db.engine import make_engine
from backend.app.presign import Presigner
from backend.app.services import compute_targets
from backend.app.services.clock import Clock, utcnow
from backend.app.storage import Buckets, make_s3_client

SessionFactory = sessionmaker[Session]


@cache
def get_sessionmaker() -> SessionFactory:
    return sessionmaker(make_engine())


@dataclass(frozen=True)
class Storage:
    buckets: Buckets
    presigner: Presigner


@cache
def get_storage() -> Storage:
    return Storage(buckets=Buckets.from_client(make_s3_client()), presigner=Presigner.from_env())


def get_clock() -> Clock:
    return utcnow


@contextmanager
def transaction(factory: SessionFactory) -> Iterator[Session]:
    with factory.begin() as session:
        yield session


def _unauthenticated() -> ApiError:
    return ApiError(
        status.HTTP_401_UNAUTHORIZED,
        ErrorCode.UNAUTHENTICATED,
        "Thiếu hoặc sai token của compute target",
    )


def bearer_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(worker_token)],
) -> str:
    """Token trong header `Authorization: Bearer`; thiếu → 401 (không cần mở DB)."""
    if credentials is None or not credentials.credentials:
        raise _unauthenticated()
    return credentials.credentials


def authenticate_worker(session: Session, token: str) -> m.ComputeTarget:
    """Token → compute target; sai (hoặc đã bị xoay) → 401."""
    target = compute_targets.authenticate(session, token)
    if target is None:
        raise _unauthenticated()
    return target
