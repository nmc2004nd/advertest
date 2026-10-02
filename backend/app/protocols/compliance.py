"""Tuân thủ protocol (requirements.md Phase 8, Tuân thủ protocol khi tạo experiment; plan task 9).

Dùng chung cho ước lượng, tạo experiment, `ExperimentDetail.compliance` và gửi duyệt. Protocol
`dev` không có yêu cầu nên danh sách rỗng. Mỗi mục `ComplianceItem` một điều kiện; mục theo
attack ghi `attack_spec_name`. Attack bắt buộc vắng mặt hoặc sai version, sai chế độ thì bỏ các
mục chi tiết của attack đó (không có cấu hình để so).
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from advertest_contracts.enums import ComplianceCode, ProtocolStatus, RunMode
from advertest_contracts.models import (
    AttackConfig,
    AttackSpec,
    ComplianceItem,
    ProtocolBody,
    RequiredAttack,
)
from backend.app.db import models as m

C = ComplianceCode


def _item(code: ComplianceCode, ok: bool, detail: str, name: str | None = None) -> ComplianceItem:
    return ComplianceItem(code=code, attack_spec_name=name, satisfied=ok, detail=detail)


def _levels(values: Sequence[float]) -> str:
    return ", ".join(f"{v:g}" for v in values)


def evaluate(
    session: Session,
    *,
    protocol: m.Protocol,
    attacks: Sequence[tuple[AttackConfig, AttackSpec]],
    slice_size: int,
    supports_gradients: bool,
    for_creation: bool,
) -> list[ComplianceItem]:
    """Mọi mục tuân thủ của cấu hình với protocol. `for_creation` thêm mục `protocol_active`
    (tạo mới chỉ với protocol `active`; experiment cũ gắn protocol đã `retired` vẫn hợp lệ)."""
    if protocol.status == ProtocolStatus.DEV:
        return []
    body = ProtocolBody.model_validate(protocol.body)
    items: list[ComplianceItem] = []
    if for_creation:
        active = protocol.status == ProtocolStatus.ACTIVE
        items.append(
            _item(
                C.PROTOCOL_ACTIVE,
                active,
                f"Protocol {protocol.name} v{protocol.version}"
                + ("" if active else f" đang ở trạng thái {protocol.status}"),
            )
        )
    by_name = {spec.name: (attack, spec) for attack, spec in attacks}
    for required in body.required_attacks:
        items.extend(_attack_items(required, by_name.get(required.attack_spec_name)))
    items.append(
        _item(
            C.MIN_SLICE_SIZE,
            slice_size >= body.min_slice_size,
            f"Slice {slice_size} ảnh, protocol cần tối thiểu {body.min_slice_size}",
        )
    )
    needs = _needs_gradients(session, body)
    if needs:
        detail = f"Attack bắt buộc cần gradient: {', '.join(needs)}; model " + (
            "hỗ trợ gradient" if supports_gradients else "không hỗ trợ gradient"
        )
        items.append(_item(C.MODEL_GRADIENTS, supports_gradients, detail))
    else:
        items.append(_item(C.MODEL_GRADIENTS, True, "Không có attack bắt buộc cần gradient"))
    return items


def _attack_items(
    required: RequiredAttack, found: tuple[AttackConfig, AttackSpec] | None
) -> list[ComplianceItem]:
    name = required.attack_spec_name
    if found is None:
        return [_item(C.ATTACK_PRESENT, False, f"Thiếu attack bắt buộc {name}", name)]
    attack, spec = found
    items = [_item(C.ATTACK_PRESENT, True, f"Có {name}", name)]
    same_spec = attack.spec_sha256 == required.spec_sha256
    items.append(
        _item(
            C.SPEC_SHA256,
            same_spec,
            f"{name} v{spec.version}"
            + ("" if same_spec else ": khác version spec mà protocol yêu cầu"),
            name,
        )
    )
    same_mode = attack.mode == required.mode
    mode_name = {RunMode.GRID: "quét lưới", RunMode.SEARCH: "tự tìm ngưỡng"}
    items.append(
        _item(
            C.MODE,
            same_mode,
            f"Protocol yêu cầu {mode_name[required.mode]}"
            + ("" if same_mode else f", cấu hình đang {mode_name[attack.mode]}"),
            name,
        )
    )
    if not same_mode:
        return items
    if required.grid is not None:
        assert attack.grid is not None  # cùng chế độ quét lưới
        missing = [lv for lv in required.grid.levels if lv not in attack.grid.levels]
        detail = (
            f"Thiếu level {_levels(missing)}"
            if missing
            else f"Đủ level bắt buộc {_levels(required.grid.levels)}"
        )
        items.append(_item(C.GRID_LEVELS, not missing, detail, name))
        return items
    need = required.search
    have = attack.search
    assert need is not None and have is not None  # cùng chế độ tìm ngưỡng
    same_threshold = (have.threshold_kind, have.threshold, have.class_filter) == (
        need.threshold_kind,
        need.threshold,
        need.class_filter,
    )
    target = f"{need.threshold_kind} {need.threshold:g}" + (
        f" (class {need.class_filter})" if need.class_filter else ""
    )
    items.append(
        _item(
            C.SEARCH_THRESHOLD,
            same_threshold,
            f"Protocol yêu cầu ngưỡng {target}" + ("" if same_threshold else "; cấu hình khác"),
            name,
        )
    )
    covers = have.lo <= need.lo and have.hi >= need.hi
    items.append(
        _item(
            C.SEARCH_RANGE,
            covers,
            f"Dải [{have.lo:g}, {have.hi:g}] phải bao phủ [{need.lo:g}, {need.hi:g}]",
            name,
        )
    )
    items.append(
        _item(
            C.SEARCH_TOL,
            have.tol <= need.max_tol,
            f"Độ chính xác {have.tol:g}, tối đa {need.max_tol:g}",
            name,
        )
    )
    items.append(
        _item(
            C.SEARCH_BOOTSTRAP,
            have.bootstrap_samples >= need.min_bootstrap_samples,
            f"{have.bootstrap_samples} mẫu bootstrap, tối thiểu {need.min_bootstrap_samples}",
            name,
        )
    )
    return items


def _needs_gradients(session: Session, body: ProtocolBody) -> list[str]:
    """Tên attack bắt buộc cần gradient (đọc spec theo `spec_sha256` trong catalog)."""
    hashes = [r.spec_sha256 for r in body.required_attacks]
    if not hashes:
        return []
    rows = session.execute(
        select(m.AttackSpecRow.name, m.AttackSpecRow.spec).where(
            m.AttackSpecRow.spec_sha256.in_(hashes)
        )
    )
    return sorted({name for name, spec in rows if spec.get("requires_gradients")})


def satisfied(items: Sequence[ComplianceItem]) -> bool:
    return all(item.satisfied for item in items)
