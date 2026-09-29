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
DEFAULT_MAX_TIME_LIMIT_S = 28800  # requirements.md Phase 5: trần người dùng được chọn (8 giờ)


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
        "max_time_limit_s": target.max_time_limit_s,
    }


def _check_limits(default_s: int, max_s: int) -> None:
    if default_s <= 0:
        raise Invalid("Giới hạn thời gian phải lớn hơn 0")
    if default_s > max_s:
        raise Invalid(
            f"Giới hạn mặc định ({default_s} s) không được lớn hơn giới hạn tối đa ({max_s} s)"
        )


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
    max_time_limit_s: int = DEFAULT_MAX_TIME_LIMIT_S,
) -> IssuedToken:
    if kind != ComputeKind.LOCAL or billing_mode != BillingMode.NONE:
        raise Invalid("Phase 3 chỉ nhận compute target kind = local, billing_mode = none")
    _check_limits(time_limit_s, max_time_limit_s)
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
        max_time_limit_s=max_time_limit_s,
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


def set_limits(
    session: Session,
    *,
    actor: m.User,
    name: str,
    default_s: int | None = None,
    max_s: int | None = None,
) -> m.ComputeTarget:
    """Đổi giới hạn thời gian mặc định và tối đa (requirements.md Phase 5: admin sửa qua
    `advertest-admin`). Experiment đã tạo giữ giới hạn của nó."""
    target = get_by_name(session, name)
    before = _summary(target)
    new_default = target.default_time_limit_s if default_s is None else default_s
    new_max = target.max_time_limit_s if max_s is None else max_s
    _check_limits(new_default, new_max)
    target.default_time_limit_s = new_default
    target.max_time_limit_s = new_max
    session.flush()
    audit.record(
        session,
        actor=actor,
        action="compute_target.update_limits",
        entity_type="compute_target",
        entity_id=target.id,
        before=before,
        after=_summary(target),
    )
    return target


def authenticate(session: Session, token: str) -> m.ComputeTarget | None:
    if not token:
        return None
    return session.scalar(
        select(m.ComputeTarget).where(m.ComputeTarget.token_hash == hash_token(token))
    )


def list_targets(session: Session) -> list[m.ComputeTarget]:
    return list(session.scalars(select(m.ComputeTarget).order_by(m.ComputeTarget.name)))
