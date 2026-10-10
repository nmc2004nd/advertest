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

from sqlalchemy import select
from sqlalchemy.orm import Session

from advertest_contracts.enums import (
    ComputeKind,
    ErrorCode,
    ExperimentStatus,
    LimitKind,
    ModelStatus,
    ProtocolStatus,
    RunMode,
    RunStatus,
    ThresholdKind,
)
from advertest_contracts.models import (
    AttackConfig,
    AttackSpec,
    ComplianceItem,
    ExperimentCreate,
    FieldError,
    PrimaryParam,
    RunMetrics,
)
from backend.app.db import models as m
from backend.app.protocols import compliance
from backend.app.services.errors import InvalidConfig
from ml_core.search.bounds import search_bounds

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
    # Phase 7: giới hạn số điểm của attack tìm ngưỡng, theo attack_spec_id.
    max_points: dict[UUID, int] = field(default_factory=dict)
    # Phase 8: tuân thủ protocol (rỗng với protocol dev).
    compliance: list[ComplianceItem] = field(default_factory=list)

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


def level_errors(param: PrimaryParam, levels: list[float], path: str) -> list[FieldError]:
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


def check(
    session: Session, body: ExperimentCreate, *, enforce_compliance: bool = True
) -> CheckedConfig:
    """Trả cấu hình đã kiểm tra, hoặc ném `InvalidConfig` với mọi lỗi tìm được.

    Phase 8: cấu hình hợp lệ thì tính tuân thủ protocol (`CheckedConfig.compliance`). Khi tạo
    experiment (`enforce_compliance`), không tuân thủ → `InvalidConfig` mã `not_compliant` kèm
    mọi mục; ước lượng chỉ trả danh sách để wizard hiển thị."""
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
    # Phase 7: (đường dẫn trường, attack, spec) tìm ngưỡng, kiểm tra tiếp sau khi có slice.
    searches: list[tuple[str, AttackConfig, AttackSpec]] = []
    for i, attack in enumerate(body.attacks):
        prefix = f"attacks.{i}"
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
        if attack.mode == RunMode.SEARCH:
            if spec.requires_training:
                not_supported = True
                error(
                    f"{prefix}.mode",
                    f"{spec.name} cần train patch cho mỗi điểm nên chưa hỗ trợ tự tìm ngưỡng;"
                    " hãy dùng quét lưới",
                )
                continue
            errors.extend(_search_errors(spec, attack, prefix))
            searches.append((prefix, attack, spec))
            continue
        assert attack.grid is not None  # mode = grid: schema bắt buộc có grid
        levels = attack.grid.levels
        errors.extend(level_errors(spec.primary_param, levels, f"{prefix}.grid.levels"))
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
    # ------------------------------------------------------------ model, slice, mapping
    model = session.get(m.ModelVersion, body.model_version_id)
    if model is None:
        error("model_version_id", "Không có model này")
    elif model.status != ModelStatus.READY:
        # Phase R2: model đăng ký qua web chỉ dùng được sau khi job model_check pass.
        error("model_version_id", f"Model chưa sẵn sàng ({model.status})")
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

    # ------------------------------------------------------------ tìm ngưỡng (Phase 7)
    max_points: dict[UUID, int] = {}
    if slice_row is not None:
        images = len(slice_row.image_ids)
        targets = _target_classes(mapping) if mapping is not None else None
        clean = (
            _known_clean_metrics(session, model.id, slice_row.id, mapping.id)
            if model is not None and mapping is not None
            else None
        )
        for prefix, attack, spec in searches:
            search = attack.search
            assert search is not None  # mode = search: schema bắt buộc có search
            if search.subset_size > images:
                error(
                    f"{prefix}.search.subset_size",
                    f"Tập con tối đa bằng số ảnh của slice ({images})",
                )
            if (
                targets is not None
                and search.class_filter is not None
                and search.class_filter not in targets
            ):
                error(
                    f"{prefix}.search.class_filter",
                    f"{search.class_filter} không phải class đích của mapping",
                )
            if search.threshold_kind == ThresholdKind.ABSOLUTE_DROP and clean is not None:
                bound = _clean_ap(clean, search.class_filter)
                if bound is not None and search.threshold > bound:
                    error(
                        f"{prefix}.search.threshold",
                        f"Mức sụt tuyệt đối tối đa bằng mAP@0.5 sạch ({bound:.3f})",
                    )
            try:
                max_points[spec.id] = search_bounds(search, spec.primary_param, images).max_points
            except ValueError as exc:  # dải không hợp lệ đã báo ở `_search_errors`
                if not any(e.path.startswith(f"{prefix}.search") for e in errors):
                    error(f"{prefix}.search", str(exc))
    total_runs += sum(max_points.values())
    if total_runs > MAX_RUNS:
        error(
            "attacks",
            f"Tối đa {MAX_RUNS} run mỗi experiment, tính cả số điểm tối đa của tự tìm ngưỡng"
            f" (đang có {total_runs})",
        )

    if body.cloned_from is not None and session.get(m.Experiment, body.cloned_from) is None:
        error("cloned_from", "Không có experiment gốc này")
    if body.promoted_from is not None:
        problem = promoted_from_problem(session, body.promoted_from)
        if problem is not None:
            error("promoted_from", problem)

    if errors:
        code = ErrorCode.NOT_SUPPORTED_YET if not_supported else ErrorCode.INVALID_REQUEST
        raise InvalidConfig(f"Cấu hình experiment không hợp lệ ({len(errors)} lỗi)", errors, code)
    assert model is not None and slice_row is not None and mapping is not None
    assert protocol is not None and target is not None
    items = compliance.evaluate(
        session,
        protocol=protocol,
        attacks=list(zip(body.attacks, specs, strict=True)),
        slice_size=len(slice_row.image_ids),
        supports_gradients=model.supports_gradients,
        for_creation=True,
    )
    if enforce_compliance and not compliance.satisfied(items):
        missing = sum(1 for item in items if not item.satisfied)
        raise InvalidConfig(
            f"Cấu hình chưa tuân thủ protocol {protocol.name} v{protocol.version}"
            f" ({missing} mục chưa thỏa)",
            [],
            ErrorCode.NOT_COMPLIANT,
            compliance=items,
        )
    return CheckedConfig(
        body,
        model,
        slice_row,
        mapping,
        protocol,
        target,
        specs,
        {row.id: row for _, _, row in training},
        max_points,
        items,
    )


def _search_errors(spec: AttackSpec, attack: AttackConfig, prefix: str) -> list[FieldError]:
    """Phase 7: dải tìm kiếm trong dải của spec; tham số rời rạc thì `lo`, `hi` là giá trị của
    spec. Miền của `threshold`, `tol`, `coarse_n`, `subset_size` tối thiểu đã kiểm ở contract."""
    search = attack.search
    assert search is not None
    param = spec.primary_param
    errors: list[FieldError] = []
    unit = f" {param.unit}" if param.unit else ""
    rule = f"dải [{_format_level(param.min)}, {_format_level(param.max)}]{unit}"
    for name, value in (("lo", search.lo), ("hi", search.hi)):
        path = f"{prefix}.search.{name}"
        if not param.min <= value <= param.max:
            errors.append(FieldError(path=path, message=f"{_format_level(value)} ngoài {rule}"))
        elif param.type == "discrete" and param.values is not None and value not in param.values:
            allowed = ", ".join(_format_level(v) for v in param.values)
            errors.append(FieldError(path=path, message=f"Chỉ nhận {allowed}"))
    if attack.training_slice_id is not None:
        errors.append(
            FieldError(
                path=f"{prefix}.training_slice_id",
                message=f"{spec.name} không cần slice huấn luyện",
            )
        )
    return errors


def _target_classes(mapping: m.ClassMapping) -> set[str]:
    classes = mapping.mapping.get("classes", {})
    return {c for c in classes.values() if c is not None}


def _known_clean_metrics(
    session: Session, model_id: UUID, slice_id: UUID, mapping_id: UUID
) -> RunMetrics | None:
    """Metric sạch đã biết của (model, slice, mapping) từ một run đã có metric đầy đủ (quyết
    định Group 4: chỉ kiểm cận của `absolute_drop` khi đã biết mAP sạch)."""
    row = session.scalar(
        select(m.Run.metrics)
        .join(m.Experiment, m.Experiment.id == m.Run.experiment_id)
        .where(
            m.Experiment.model_version_id == model_id,
            m.Experiment.slice_id == slice_id,
            m.Experiment.class_mapping_id == mapping_id,
            m.Run.status == RunStatus.COMPLETED,
            m.Run.scope == "full",
            m.Run.metrics.is_not(None),
        )
        .limit(1)
    )
    return RunMetrics.model_validate(row) if row is not None else None


def _clean_ap(metrics: RunMetrics, class_filter: str | None) -> float | None:
    if class_filter is None:
        return metrics.clean.map50
    per_class = metrics.per_class or {}
    found = per_class.get(class_filter)
    return found.clean_ap50 if found is not None else None


# Experiment đã kết thúc (`stopped_limit` là trạng thái của run, không phải của experiment).
FINISHED = (ExperimentStatus.COMPLETED, ExperimentStatus.CANCELLED)


def promoted_from_problem(session: Session, experiment_id: UUID) -> str | None:
    """Lý do `promoted_from` không hợp lệ, hoặc None: nguồn phải là experiment Khám phá (protocol
    `dev`) đã kết thúc (Chốt ở Group 1, review #4)."""
    source = session.get(m.Experiment, experiment_id)
    if source is None:
        return "Không có experiment Khám phá nguồn này"
    protocol = session.get(m.Protocol, source.protocol_id)
    if protocol is None or protocol.status != ProtocolStatus.DEV:
        return "Experiment nguồn không phải experiment Khám phá"
    if source.status not in FINISHED:
        return (
            f"Experiment nguồn đang ở trạng thái {source.status}; chỉ nâng experiment đã kết thúc"
        )
    return None
