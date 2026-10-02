"""Protocol có version (requirements.md Phase 8, mục Protocol; plan task 8).

- Nội dung một version không bao giờ đổi: chỉ thêm bản ghi mới.
- Tạo version mới chỉ từ version mới nhất của `name` (409 nếu không); version cũ đang `active`
  chuyển `retired` trong cùng giao dịch (chốt ở Group 0).
- Kiểm tra cần catalog (contract đã kiểm phần không cần DB): spec có trong catalog, đang hoạt
  động, đúng `spec_sha256`; patch không ở chế độ tìm ngưỡng; level và dải trong `primary_param`;
  tổng run bắt buộc (level quét lưới cộng `max_points` của tìm ngưỡng với `tol = max_tol`,
  `coarse_n` mặc định, có giai đoạn tập con) không vượt `MAX_RUNS`.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from advertest_contracts.enums import ErrorCode, ProtocolStatus, RunMode
from advertest_contracts.hashing import sha256_of
from advertest_contracts.models import (
    FieldError,
    PrimaryParam,
    ProtocolBody,
    ProtocolCreate,
    ProtocolVersionCreate,
    ProtocolView,
    SearchConfig,
    UserRef,
)
from backend.app.db import models as m
from backend.app.services import audit
from backend.app.services.errors import Conflict, InvalidConfig, NotFound
from backend.app.services.experiment_config import MAX_RUNS, level_errors, spec_of
from ml_core.search.bounds import search_bounds

ENTITY = "protocol"


def view(session: Session, row: m.Protocol) -> ProtocolView:
    creator = session.get(m.User, row.created_by) if row.created_by is not None else None
    return ProtocolView(
        id=row.id,
        name=row.name,
        version=row.version,
        status=row.status,
        body=ProtocolBody.model_validate(row.body),
        body_sha256=row.body_sha256,
        created_by=UserRef(id=creator.id, full_name=creator.full_name) if creator else None,
        created_at=row.created_at,
    )


def get(session: Session, protocol_id: UUID) -> ProtocolView:
    row = session.get(m.Protocol, protocol_id)
    if row is None:
        raise NotFound("Không có protocol này")
    return view(session, row)


def create(session: Session, *, actor: m.User, body: ProtocolCreate) -> ProtocolView:
    """Protocol `active` version 1 (409 khi đã có protocol cùng tên: dùng tạo version mới)."""
    exists = session.scalar(select(m.Protocol.id).where(m.Protocol.name == body.name).limit(1))
    if exists is not None:
        raise Conflict(f"Đã có protocol {body.name}; hãy tạo version mới của protocol đó")
    check_catalog(session, body.body)
    row = _insert(session, actor=actor, name=body.name, version=1, body=body.body)
    audit.record(
        session,
        actor=actor,
        action="protocol.created",
        entity_type=ENTITY,
        entity_id=row.id,
        after=_summary(row),
    )
    return view(session, row)


def create_version(
    session: Session, *, actor: m.User, protocol_id: UUID, body: ProtocolVersionCreate
) -> ProtocolView:
    base = session.scalar(select(m.Protocol).where(m.Protocol.id == protocol_id).with_for_update())
    if base is None:
        raise NotFound("Không có protocol này")
    if base.status == ProtocolStatus.DEV:
        raise Conflict("Protocol phát triển không có version mới")
    latest = session.scalar(
        select(func.max(m.Protocol.version)).where(m.Protocol.name == base.name)
    )
    if base.version != latest:
        raise Conflict(
            f"{base.name} v{base.version} không phải version mới nhất (v{latest});"
            " hãy tạo version mới từ bản mới nhất"
        )
    check_catalog(session, body.body)
    if base.status == ProtocolStatus.ACTIVE:
        _retire(session, actor=actor, row=base)
    row = _insert(session, actor=actor, name=base.name, version=base.version + 1, body=body.body)
    audit.record(
        session,
        actor=actor,
        action="protocol.versioned",
        entity_type=ENTITY,
        entity_id=row.id,
        before={"protocol_id": str(base.id), "version": base.version},
        after=_summary(row),
    )
    return view(session, row)


def retire(session: Session, *, actor: m.User, protocol_id: UUID) -> ProtocolView:
    """`active` → `retired` (409 với trạng thái khác); experiment đã tạo không bị ảnh hưởng."""
    row = session.scalar(select(m.Protocol).where(m.Protocol.id == protocol_id).with_for_update())
    if row is None:
        raise NotFound("Không có protocol này")
    if row.status != ProtocolStatus.ACTIVE:
        raise Conflict(f"Protocol {row.name} v{row.version} đang ở trạng thái {row.status}")
    _retire(session, actor=actor, row=row)
    return view(session, row)


def _retire(session: Session, *, actor: m.User, row: m.Protocol) -> None:
    row.status = ProtocolStatus.RETIRED
    audit.record(
        session,
        actor=actor,
        action="protocol.retired",
        entity_type=ENTITY,
        entity_id=row.id,
        before={"status": ProtocolStatus.ACTIVE.value},
        after={"status": ProtocolStatus.RETIRED.value},
    )


def _insert(
    session: Session, *, actor: m.User, name: str, version: int, body: ProtocolBody
) -> m.Protocol:
    row = m.Protocol(
        name=name,
        version=version,
        body=body.model_dump(mode="json"),
        body_sha256=sha256_of(body),
        status=ProtocolStatus.ACTIVE,
        created_by=actor.id,
    )
    # Hai request đồng thời cùng tên (hoặc cùng version mới) qua được kiểm tra trước đó: ràng
    # buộc unique (name, version) chặn bản thứ hai, trả 409 thay vì 500 (review Group 1 #2).
    try:
        with session.begin_nested():
            session.add(row)
            session.flush()
    except IntegrityError as exc:
        raise Conflict(f"{name} v{version} vừa được tạo bởi request khác; hãy tải lại") from exc
    session.refresh(row)
    return row


def _summary(row: m.Protocol) -> dict[str, object]:
    return {"name": row.name, "version": row.version, "body_sha256": row.body_sha256}


# ---------------------------------------------------------------- kiểm tra cần catalog


def check_catalog(session: Session, body: ProtocolBody) -> None:
    """Ném `InvalidConfig` (422 `invalid_request`) với mọi lỗi; đường dẫn trường bắt đầu bằng
    `body.` như trong request."""
    errors: list[FieldError] = []
    total_runs = 0
    # Có giai đoạn tập con: slice lớn hơn tập con mặc định (chi phí xấu nhất).
    images = max(body.min_slice_size, SearchConfig.model_fields["subset_size"].default + 1)
    for i, required in enumerate(body.required_attacks):
        path = f"body.required_attacks.{i}"
        row = session.scalar(
            select(m.AttackSpecRow).where(
                m.AttackSpecRow.name == required.attack_spec_name,
                m.AttackSpecRow.spec_sha256 == required.spec_sha256,
            )
        )
        if row is None:
            errors.append(
                FieldError(
                    path=f"{path}.spec_sha256",
                    message=f"Không có {required.attack_spec_name} với spec_sha256 này trong"
                    " catalog",
                )
            )
            continue
        if not row.is_active:
            errors.append(
                FieldError(
                    path=f"{path}.spec_sha256",
                    message=f"{row.name} v{row.version} không còn hoạt động; chọn version"
                    " hiện hành",
                )
            )
        spec = spec_of(row)
        param = spec.primary_param
        if required.mode == RunMode.GRID:
            assert required.grid is not None  # contract: mode = grid có grid
            errors.extend(level_errors(param, required.grid.levels, f"{path}.grid.levels"))
            total_runs += len(required.grid.levels)
            continue
        search = required.search
        assert search is not None  # contract: mode = search có search
        if spec.requires_training:
            errors.append(
                FieldError(
                    path=f"{path}.mode",
                    message=f"{spec.name} cần train patch cho mỗi điểm nên không dùng được ở"
                    " chế độ tìm ngưỡng",
                )
            )
            continue
        range_errors = _range_errors(param, search.lo, search.hi, f"{path}.search")
        errors.extend(range_errors)
        if range_errors:
            continue
        config = SearchConfig(
            threshold_kind=search.threshold_kind,
            threshold=search.threshold,
            lo=search.lo,
            hi=search.hi,
            tol=search.max_tol,
            class_filter=search.class_filter,
            bootstrap_samples=search.min_bootstrap_samples,
        )
        try:
            total_runs += search_bounds(config, param, images).max_points
        except ValueError as exc:
            errors.append(FieldError(path=f"{path}.search", message=str(exc)))
    if total_runs > MAX_RUNS:
        errors.append(
            FieldError(
                path="body.required_attacks",
                message=f"Attack bắt buộc cần tới {total_runs} run (tính cả số điểm tối đa của"
                f" tự tìm ngưỡng với max_tol); tối đa {MAX_RUNS} nên không experiment nào tuân"
                " thủ được",
            )
        )
    if errors:
        raise InvalidConfig(
            f"Protocol không hợp lệ ({len(errors)} lỗi)", errors, ErrorCode.INVALID_REQUEST
        )


def _range_errors(param: PrimaryParam, lo: float, hi: float, prefix: str) -> list[FieldError]:
    errors: list[FieldError] = []
    for name, value in (("lo", lo), ("hi", hi)):
        if not param.min <= value <= param.max:
            errors.append(
                FieldError(
                    path=f"{prefix}.{name}",
                    message=f"{value:g} ngoài dải [{param.min:g}, {param.max:g}] {param.unit}",
                )
            )
        elif param.type == "discrete" and param.values is not None and value not in param.values:
            allowed = ", ".join(f"{v:g}" for v in param.values)
            errors.append(FieldError(path=f"{prefix}.{name}", message=f"Chỉ nhận {allowed}"))
    return errors
