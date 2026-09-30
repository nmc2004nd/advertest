"""Kiểm tra cấu hình experiment, dùng chung cho ước lượng và tạo (requirements.md Phase 5, Kiểm
tra khi tạo và ước lượng).

Gom mọi lỗi cùng lúc, mỗi lỗi gắn đường dẫn trường trong body (`attacks.0.grid.levels`) để
giao diện hiển thị tại đúng bước và đúng trường. Giới hạn số experiment đang chờ (409) không
nằm ở đây: chỉ kiểm tra khi tạo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from advertest_contracts.enums import ComputeKind, ErrorCode, LimitKind, ProtocolStatus, RunMode
from advertest_contracts.models import AttackSpec, ExperimentCreate, FieldError, PrimaryParam
from backend.app.db import models as m
from backend.app.services.errors import InvalidConfig

MAX_LEVELS_PER_ATTACK = 12
MAX_RUNS = 50
ALLOWED_PROTOCOLS = (ProtocolStatus.ACTIVE, ProtocolStatus.DEV)


@dataclass(frozen=True)
class CheckedConfig:
    """Cấu hình đã hợp lệ, kèm các bản ghi đã đọc (không phải đọc lại khi ước lượng hay tạo)."""

    body: ExperimentCreate
    model: m.ModelVersion
    slice: m.Slice
    mapping: m.ClassMapping
    protocol: m.Protocol
    target: m.ComputeTarget
    specs: list[AttackSpec]  # theo thứ tự `body.attacks`
    # Phase 6: slice huấn luyện của attack cần train, theo id.
    training_slices: dict[UUID, m.Slice] = field(default_factory=dict)

    @property
    def images(self) -> int:
        return len(self.slice.image_ids)

    @property
    def limit_seconds(self) -> Decimal:
        return self.body.limit.value


def spec_of(row: m.AttackSpecRow) -> AttackSpec:
    return AttackSpec.model_validate(
        {**row.spec, "id": str(row.id), "spec_sha256": row.spec_sha256}
    )


def _format_level(value: float) -> str:
    return f"{value:g}"


def _level_errors(param: PrimaryParam, levels: list[float], path: str) -> list[FieldError]:
    errors: list[FieldError] = []
    unit = f" {param.unit}" if param.unit else ""
    if param.type == "discrete" and param.values is not None:
        allowed = set(param.values)
        outside = [lv for lv in levels if lv not in allowed]
        rule = "chỉ nhận " + ", ".join(_format_level(v) for v in param.values)
    else:
        outside = [lv for lv in levels if not param.min <= lv <= param.max]
        rule = f"dải [{_format_level(param.min)}, {_format_level(param.max)}]{unit}"
    if outside:
        values = ", ".join(_format_level(lv) for lv in outside)
        errors.append(FieldError(path=path, message=f"Level {values} ngoài {rule}"))
    duplicates = sorted({lv for lv in levels if levels.count(lv) > 1})
    if duplicates:
        values = ", ".join(_format_level(lv) for lv in duplicates)
        errors.append(FieldError(path=path, message=f"Level bị trùng: {values}"))
    if len(levels) > MAX_LEVELS_PER_ATTACK:
        errors.append(
            FieldError(
                path=path,
                message=f"Tối đa {MAX_LEVELS_PER_ATTACK} level mỗi attack (đang có {len(levels)})",
            )
        )
    return errors


def check(session: Session, body: ExperimentCreate) -> CheckedConfig:
    """Trả cấu hình đã kiểm tra, hoặc ném `InvalidConfig` với mọi lỗi tìm được."""
    errors: list[FieldError] = []
    not_supported = False

    def error(path: str, message: str) -> None:
        errors.append(FieldError(path=path, message=message))

    # ------------------------------------------------------------ attack
    specs: list[AttackSpec] = []
    # Phase 6: (đường dẫn trường, spec, slice huấn luyện) kiểm tra sau khi có slice đánh giá.
    training: list[tuple[str, AttackSpec, m.Slice]] = []
    seen: dict[object, int] = {}
    total_runs = 0
    for i, attack in enumerate(body.attacks):
        prefix = f"attacks.{i}"
        if attack.mode == RunMode.SEARCH:
            not_supported = True
            error(f"{prefix}.mode", "Chế độ tự tìm ngưỡng chưa có; hãy dùng quét lưới")
            continue
        if attack.attack_spec_id in seen:
            error(
                f"{prefix}.attack_spec_id",
                f"Attack này đã có ở attacks.{seen[attack.attack_spec_id]}; gộp các level lại",
            )
        seen.setdefault(attack.attack_spec_id, i)
        row = session.get(m.AttackSpecRow, attack.attack_spec_id)
        if row is None:
            error(f"{prefix}.attack_spec_id", "Không có attack spec này trong catalog")
            continue
        if not row.is_active:
            error(
                f"{prefix}.attack_spec_id",
                f"{row.name} v{row.version} không còn hoạt động; chọn version hiện hành",
            )
        if row.spec_sha256 != attack.spec_sha256:
            error(
                f"{prefix}.spec_sha256",
                f"spec_sha256 không khớp {row.name} v{row.version} hiện hành",
            )
        spec = spec_of(row)
        specs.append(spec)
        assert attack.grid is not None  # mode = grid: schema bắt buộc có grid
        levels = attack.grid.levels
        errors.extend(_level_errors(spec.primary_param, levels, f"{prefix}.grid.levels"))
        total_runs += len(levels)
        path = f"{prefix}.training_slice_id"
        if spec.requires_training:
            if attack.training_slice_id is None:
                error(path, f"{spec.name} cần slice huấn luyện (không giao với slice đánh giá)")
            else:
                training_row = session.get(m.Slice, attack.training_slice_id)
                if training_row is None:
                    error(path, "Không có slice huấn luyện này")
                else:
                    training.append((path, spec, training_row))
        elif attack.training_slice_id is not None:
            error(path, f"{spec.name} không cần slice huấn luyện")
    if total_runs > MAX_RUNS:
        error("attacks", f"Tối đa {MAX_RUNS} run mỗi experiment (đang có {total_runs})")

    # ------------------------------------------------------------ model, slice, mapping
    model = session.get(m.ModelVersion, body.model_version_id)
    if model is None:
        error("model_version_id", "Không có model này")
    slice_row = session.get(m.Slice, body.slice_id)
    if slice_row is None:
        error("slice_id", "Không có slice này")
    mapping = session.get(m.ClassMapping, body.class_mapping_id)
    if mapping is None:
        error("class_mapping_id", "Không có class mapping này")
    else:
        if model is not None and mapping.model_version_id != model.id:
            error("class_mapping_id", "Class mapping không dành cho model đã chọn")
        if slice_row is not None and mapping.dataset_version_id != slice_row.dataset_version_id:
            error("slice_id", "Slice không thuộc dataset version của class mapping")

    # ------------------------------------------------------------ protocol
    protocol = session.get(m.Protocol, body.protocol_id)
    if protocol is None:
        error("protocol_id", "Không có protocol này")
    elif protocol.status not in ALLOWED_PROTOCOLS:
        error("protocol_id", f"Protocol {protocol.name} đang ở trạng thái {protocol.status}")

    # ------------------------------------------------------------ máy chạy và giới hạn
    target = session.get(m.ComputeTarget, body.compute_target_id)
    if target is None:
        error("compute_target_id", "Không có máy chạy này")
    elif target.kind != ComputeKind.LOCAL:
        error("compute_target_id", "Phiên bản này chỉ chạy trên máy local")
    else:
        if body.limit.kind != LimitKind.TIME:
            error("limit.kind", "Máy local dùng giới hạn thời gian (time)")
        elif body.limit.value > target.max_time_limit_s:
            error(
                "limit.value",
                f"Giới hạn tối đa của {target.name} là {target.max_time_limit_s} giây",
            )

    # ------------------------------------------------------------ slice huấn luyện (Phase 6)
    if slice_row is not None:
        evaluation = set(slice_row.image_ids)
        for path, spec, training_row in training:
            if training_row.dataset_version_id != slice_row.dataset_version_id:
                error(path, "Slice huấn luyện phải cùng dataset version với slice đánh giá")
            common = evaluation.intersection(training_row.image_ids)
            if common:
                error(path, f"Slice huấn luyện giao với slice đánh giá ({len(common)} ảnh chung)")
            assert spec.training is not None  # requires_training ⇒ có training (contract)
            limit = spec.training.max_training_images
            if len(training_row.image_ids) > limit:
                error(
                    path,
                    f"Slice huấn luyện có {len(training_row.image_ids)} ảnh, tối đa {limit}",
                )
            if training_row.slice_sha256 is None:
                error(path, "Slice huấn luyện chưa được đăng ký qua import-local")

    if body.cloned_from is not None and session.get(m.Experiment, body.cloned_from) is None:
        error("cloned_from", "Không có experiment gốc này")

    if errors:
        code = ErrorCode.NOT_SUPPORTED_YET if not_supported else ErrorCode.INVALID_REQUEST
        raise InvalidConfig(f"Cấu hình experiment không hợp lệ ({len(errors)} lỗi)", errors, code)
    assert model is not None and slice_row is not None and mapping is not None
    assert protocol is not None and target is not None
    return CheckedConfig(
        body,
        model,
        slice_row,
        mapping,
        protocol,
        target,
        specs,
        {row.id: row for _, _, row in training},
    )
