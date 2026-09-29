"""Compute target và token của worker (requirements.md Phase 3, mục Compute target và token).

Token chỉ được trả về một lần khi tạo hoặc xoay; DB chỉ lưu sha256 của token.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from advertest_contracts.enums import BillingMode, ComputeKind
from backend.app.db import models as m
from backend.app.services import audit
from backend.app.services.errors import Conflict, Invalid, NotFound

DEFAULT_TIME_LIMIT_S = 7200  # tech-stack.md mục 4.2


@dataclass(frozen=True)
class IssuedToken:
    target: m.ComputeTarget
    token: str  # chỉ có ở đây; không lưu ở đâu khác


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _new_token() -> str:
    return secrets.token_urlsafe(32)


def _summary(target: m.ComputeTarget) -> dict[str, Any]:
    return {
        "name": target.name,
        "kind": str(target.kind),
        "billing_mode": str(target.billing_mode),
        "gpu_model": target.gpu_model,
        "default_time_limit_s": target.default_time_limit_s,
    }


def get_by_name(session: Session, name: str) -> m.ComputeTarget:
    target = session.scalar(select(m.ComputeTarget).where(m.ComputeTarget.name == name))
    if target is None:
        raise NotFound(f"Không có compute target {name!r}")
    return target


def create(
    session: Session,
    *,
    actor: m.User,
    name: str,
    kind: ComputeKind = ComputeKind.LOCAL,
    billing_mode: BillingMode = BillingMode.NONE,
    gpu_model: str | None = None,
    vram_gb: Decimal | None = None,
    time_limit_s: int = DEFAULT_TIME_LIMIT_S,
) -> IssuedToken:
    if kind != ComputeKind.LOCAL or billing_mode != BillingMode.NONE:
        raise Invalid("Phase 3 chỉ nhận compute target kind = local, billing_mode = none")
    if time_limit_s <= 0:
        raise Invalid("Giới hạn thời gian phải lớn hơn 0")
    if session.scalar(select(m.ComputeTarget).where(m.ComputeTarget.name == name)) is not None:
        raise Conflict(f"Compute target {name!r} đã có (dùng rotate-token để cấp token mới)")
    token = _new_token()
    target = m.ComputeTarget(
        name=name,
        kind=kind,
        billing_mode=billing_mode,
        gpu_model=gpu_model,
        vram_gb=vram_gb,
        default_time_limit_s=time_limit_s,
        token_hash=hash_token(token),
    )
    session.add(target)
    session.flush()
    audit.record(
        session,
        actor=actor,
        action="compute_target.create",
        entity_type="compute_target",
        entity_id=target.id,
        after=_summary(target),
    )
    return IssuedToken(target=target, token=token)


def rotate_token(session: Session, *, actor: m.User, name: str) -> IssuedToken:
    """Token mới có hiệu lực ngay; token cũ không còn xác thực được."""
    target = get_by_name(session, name)
    token = _new_token()
    target.token_hash = hash_token(token)
    session.flush()
    audit.record(
        session,
        actor=actor,
        action="compute_target.rotate_token",
        entity_type="compute_target",
        entity_id=target.id,
        after={"name": target.name},
    )
    return IssuedToken(target=target, token=token)


def authenticate(session: Session, token: str) -> m.ComputeTarget | None:
    if not token:
        return None
    return session.scalar(
        select(m.ComputeTarget).where(m.ComputeTarget.token_hash == hash_token(token))
    )


def list_targets(session: Session) -> list[m.ComputeTarget]:
    return list(session.scalars(select(m.ComputeTarget).order_by(m.ComputeTarget.name)))
