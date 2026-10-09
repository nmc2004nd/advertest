"""Template protocol, preset experiment, bản nháp và nâng lên chính thức (requirements.md Phase R2,
Behaviour "Template, preset, gợi ý tiêu chí" và "Mode và nâng lên chính thức"; plan task 7, 8).

Mọi hàm ở đây chỉ dựng bản nháp, không tạo protocol hay experiment. Người dùng xem (và với
experiment, xem ước lượng) rồi mới `POST /protocols` hoặc `POST /experiments` (nguyên tắc 2, 5).

Công thức (Chốt ở Group 0):
- Level là `round(min + r·(max - min), 6)`; tham số rời rạc lấy giá trị gần nhất trong `values`
  (hòa lấy giá trị nhỏ hơn); bỏ level trùng.
- Tiêu chí quét lưới ở level bắt buộc thứ `(n - 1) // 2` đã sắp xếp, ngưỡng `relative_drop` theo
  `strictness`; tiêu chí tìm ngưỡng ở `lo + 0.5·(hi - lo)`, cùng ngưỡng với cấu hình tìm ngưỡng.
- Tìm ngưỡng của preset: dải `[min, max]` của spec, `tol = (hi - lo) / 256` như wizard, tập con
  không vượt số ảnh của slice.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from functools import cache
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from advertest_contracts.enums import (
    CriterionKind,
    ErrorCode,
    ExperimentStatus,
    ProtocolStatus,
    RunMode,
    ThresholdKind,
)
from advertest_contracts.models import (
    STRICTNESS_MAX_DROP,
    AttackConfig,
    AttackSpec,
    DraftNote,
    ExperimentClone,
    ExperimentCreate,
    ExperimentDraftRequest,
    ExperimentPreset,
    FieldError,
    GridConfig,
    PassCriterion,
    PrimaryParam,
    ProtocolBody,
    ProtocolCreate,
    ProtocolTemplate,
    RequiredAttack,
    RequiredGrid,
    RequiredSearch,
    SearchConfig,
)
from backend.app.db import models as m
from backend.app.services import experiment_views
from backend.app.services.errors import Conflict, InvalidConfig, NotFound
from backend.app.services.experiment_config import spec_of

SEEDS = Path(__file__).resolve().parents[3] / "contracts" / "seeds"
# Như wizard (Phase 7): độ rộng khoảng khi dừng chia đôi mặc định (hi - lo) / 256.
SEARCH_TOL_DIVISOR = 256
DEFAULT_SEED = 0
FINISHED = (ExperimentStatus.COMPLETED, ExperimentStatus.CANCELLED)


@cache
def protocol_templates() -> tuple[ProtocolTemplate, ...]:
    raw = json.loads((SEEDS / "protocol_templates.json").read_text(encoding="utf-8"))
    return tuple(ProtocolTemplate.model_validate(item) for item in raw)


@cache
def experiment_presets() -> tuple[ExperimentPreset, ...]:
    raw = json.loads((SEEDS / "experiment_presets.json").read_text(encoding="utf-8"))
    return tuple(ExperimentPreset.model_validate(item) for item in raw)


def level_at(param: PrimaryParam, ratio: float) -> float:
    value = param.min + ratio * (param.max - param.min)
    if param.type == "discrete" and param.values is not None:
        return min(param.values, key=lambda v: (abs(v - value), v))
    return round(value, 6)


def levels_at(param: PrimaryParam, ratios: Sequence[float]) -> list[float]:
    return sorted({level_at(param, r) for r in ratios})


def _active(session: Session, name: str) -> m.AttackSpecRow:
    row = experiment_views.current_version(session, name)
    if row is None:
        raise Conflict(f"{name} không còn version nào hoạt động trong catalog")
    return row


# ---------------------------------------------------------------- template protocol


def template_draft(session: Session, key: str) -> ProtocolCreate:
    """`ProtocolCreate` điền sẵn spec active, level và tiêu chí gợi ý. Chỉ phụ thuộc template và
    catalog, không phụ thuộc kết quả experiment nào (nguyên tắc 2)."""
    template = next((t for t in protocol_templates() if t.key == key), None)
    if template is None:
        raise NotFound(f"Không có template {key}")
    threshold = STRICTNESS_MAX_DROP[template.strictness]
    required: list[RequiredAttack] = []
    criteria: list[PassCriterion] = []
    for item in template.attacks:
        row = _active(session, item.attack_spec_name)
        param = spec_of(row).primary_param
        if item.grid is not None:
            levels = levels_at(param, item.grid.level_ratios)
            required.append(
                RequiredAttack(
                    attack_spec_name=row.name,
                    spec_sha256=row.spec_sha256,
                    mode=RunMode.GRID,
                    grid=RequiredGrid(levels=levels),
                )
            )
            criteria.append(
                PassCriterion(
                    kind=CriterionKind.MAX_DROP_AT_LEVEL,
                    attack_spec_name=row.name,
                    level=levels[(len(levels) - 1) // 2],
                    threshold_kind=ThresholdKind.RELATIVE_DROP,
                    threshold=threshold,
                )
            )
            continue
        search = item.search
        assert search is not None  # mode = search: contract bắt buộc có search
        lo = level_at(param, search.lo_ratio)
        hi = level_at(param, search.hi_ratio)
        required.append(
            RequiredAttack(
                attack_spec_name=row.name,
                spec_sha256=row.spec_sha256,
                mode=RunMode.SEARCH,
                search=RequiredSearch(
                    threshold_kind=search.threshold_kind,
                    threshold=search.threshold,
                    lo=lo,
                    hi=hi,
                    max_tol=search.max_tol_ratio * (hi - lo),
                ),
            )
        )
        criteria.append(
            PassCriterion(
                kind=CriterionKind.MIN_BREAKING_POINT,
                attack_spec_name=row.name,
                level=round(lo + 0.5 * (hi - lo), 6),
                threshold_kind=search.threshold_kind,
                threshold=search.threshold,
            )
        )
    return ProtocolCreate(
        name=template.title,
        body=ProtocolBody(
            description=template.description,
            required_attacks=required,
            min_slice_size=template.min_slice_size,
            pass_criteria=criteria,
        ),
    )


# ---------------------------------------------------------------- bản nháp experiment


def _subset(size: int, images: int) -> int:
    # SearchConfig cần tập con ≥ 2 ảnh; slice nhỏ hơn để kiểm tra cấu hình báo lỗi tại trường.
    return max(2, min(size, images))


def _required_config(
    required: RequiredAttack,
    row: m.AttackSpecRow,
    *,
    extra_levels: Sequence[float],
    seed: int,
    training_slice_id: UUID | None,
    images: int,
) -> AttackConfig:
    """Attack bắt buộc của protocol: level bắt buộc hợp `extra_levels` khi quét lưới; tìm ngưỡng
    đúng dải và ngưỡng bắt buộc, `tol` không vượt `max_tol`."""
    if required.grid is not None:
        return AttackConfig(
            attack_spec_id=row.id,
            spec_sha256=row.spec_sha256,
            mode=RunMode.GRID,
            grid=GridConfig(levels=sorted({*required.grid.levels, *extra_levels})),
            seed=seed,
            training_slice_id=training_slice_id,
        )
    need = required.search
    assert need is not None  # mode = search: contract bắt buộc có search
    return AttackConfig(
        attack_spec_id=row.id,
        spec_sha256=row.spec_sha256,
        mode=RunMode.SEARCH,
        search=SearchConfig(
            threshold_kind=need.threshold_kind,
            threshold=need.threshold,
            class_filter=need.class_filter,
            lo=need.lo,
            hi=need.hi,
            tol=min((need.hi - need.lo) / SEARCH_TOL_DIVISOR, need.max_tol),
            subset_size=_subset(SearchConfig.model_fields["subset_size"].default, images),
            bootstrap_samples=max(
                SearchConfig.model_fields["bootstrap_samples"].default,
                need.min_bootstrap_samples,
            ),
        ),
        seed=seed,
    )


def _preset_config(
    spec: AttackSpec, preset: ExperimentPreset, training_slice_id: UUID | None, images: int
) -> AttackConfig:
    """Attack tự chọn (protocol dev): lưới của preset, hoặc tìm ngưỡng thay cho quét lưới khi
    preset có tìm ngưỡng và spec hỗ trợ (không áp cho patch)."""
    param = spec.primary_param
    if preset.search is not None and not spec.requires_training:
        return AttackConfig(
            attack_spec_id=spec.id,
            spec_sha256=spec.spec_sha256,
            mode=RunMode.SEARCH,
            search=SearchConfig(
                threshold_kind=preset.search.threshold_kind,
                threshold=preset.search.threshold,
                lo=param.min,
                hi=param.max,
                tol=(param.max - param.min) / SEARCH_TOL_DIVISOR,
                subset_size=_subset(preset.search.subset_size, images),
            ),
            seed=DEFAULT_SEED,
        )
    return AttackConfig(
        attack_spec_id=spec.id,
        spec_sha256=spec.spec_sha256,
        mode=RunMode.GRID,
        grid=GridConfig(levels=levels_at(param, preset.level_ratios)),
        seed=DEFAULT_SEED,
        training_slice_id=training_slice_id if spec.requires_training else None,
    )


def _slice_notes(protocol: m.Protocol, images: int) -> list[DraftNote]:
    if protocol.status == ProtocolStatus.DEV:
        return []
    need = ProtocolBody.model_validate(protocol.body).min_slice_size
    if images >= need:
        return []
    return [
        DraftNote(
            code="slice_too_small",
            message=(
                f"Slice có {images} ảnh, protocol {protocol.name} v{protocol.version} cần tối"
                f" thiểu {need}; tạo experiment từ bản nháp này sẽ bị chặn vì chưa tuân thủ"
                " protocol."
            ),
        )
    ]


def _spec_by_sha(session: Session, spec_sha256: str) -> m.AttackSpecRow | None:
    return session.scalar(select(m.AttackSpecRow).where(m.AttackSpecRow.spec_sha256 == spec_sha256))


def experiment_draft(session: Session, body: ExperimentDraftRequest) -> ExperimentClone:
    """`POST /experiments/draft`. Protocol dev: attack trong `attack_spec_ids` (null là toàn bộ
    catalog active trừ spec cần train) theo preset. Protocol khác: đúng các attack bắt buộc, lưới
    là level bắt buộc hợp lưới của preset; attack bắt buộc tìm ngưỡng giữ cấu hình của protocol."""
    preset = next(p for p in experiment_presets() if p.key == body.preset)
    protocol = session.get(m.Protocol, body.protocol_id)
    if protocol is None:
        raise NotFound("Không có protocol này")
    if protocol.status not in (ProtocolStatus.ACTIVE, ProtocolStatus.DEV):
        raise Conflict(f"Protocol {protocol.name} đang ở trạng thái {protocol.status}")
    slice_row = session.get(m.Slice, body.slice_id)
    if slice_row is None:
        raise InvalidConfig(
            "Không có slice này",
            [FieldError(path="slice_id", message="Không có slice này")],
            ErrorCode.INVALID_REQUEST,
        )
    images = len(slice_row.image_ids)
    errors: list[FieldError] = []
    attacks: list[AttackConfig] = []
    training_path = "training_slice_id"
    if protocol.status == ProtocolStatus.DEV:
        if body.attack_spec_ids is None:
            rows = [
                row
                for row in session.scalars(
                    select(m.AttackSpecRow)
                    .where(m.AttackSpecRow.is_active)
                    .order_by(m.AttackSpecRow.name, m.AttackSpecRow.version)
                )
                if not spec_of(row).requires_training
            ]
        else:
            rows = []
            for i, spec_id in enumerate(body.attack_spec_ids):
                row = session.get(m.AttackSpecRow, spec_id)
                if row is None or not row.is_active:
                    errors.append(
                        FieldError(
                            path=f"attack_spec_ids.{i}",
                            message="Không có attack spec đang hoạt động này trong catalog",
                        )
                    )
                elif row not in rows:
                    rows.append(row)
        for row in rows:
            spec = spec_of(row)
            if spec.requires_training and body.training_slice_id is None:
                errors.append(
                    FieldError(
                        path=training_path,
                        message=f"{spec.name} cần slice huấn luyện (không giao với slice đánh giá)",
                    )
                )
            attacks.append(_preset_config(spec, preset, body.training_slice_id, images))
    else:
        if body.attack_spec_ids is not None:
            errors.append(
                FieldError(
                    path="attack_spec_ids",
                    message="Chỉ chọn attack với protocol Khám phá; protocol chính thức dùng"
                    " đúng các attack bắt buộc",
                )
            )
        protocol_body = ProtocolBody.model_validate(protocol.body)
        for i, required in enumerate(protocol_body.required_attacks):
            row = _spec_by_sha(session, required.spec_sha256)
            if row is None:
                errors.append(
                    FieldError(
                        path=f"protocol_id.required_attacks.{i}",
                        message=f"Không có {required.attack_spec_name} đúng version protocol yêu"
                        " cầu trong catalog",
                    )
                )
                continue
            spec = spec_of(row)
            if spec.requires_training and body.training_slice_id is None:
                errors.append(
                    FieldError(
                        path=training_path,
                        message=f"{spec.name} cần slice huấn luyện (không giao với slice đánh giá)",
                    )
                )
            attacks.append(
                _required_config(
                    required,
                    row,
                    extra_levels=levels_at(spec.primary_param, preset.level_ratios),
                    seed=DEFAULT_SEED,
                    training_slice_id=body.training_slice_id if spec.requires_training else None,
                    images=images,
                )
            )
    if not attacks and not errors:
        errors.append(FieldError(path="attack_spec_ids", message="Chưa có attack nào"))
    if errors:
        raise InvalidConfig(
            f"Không dựng được bản nháp ({len(errors)} lỗi)", errors, ErrorCode.INVALID_REQUEST
        )
    config = ExperimentCreate(
        protocol_id=protocol.id,
        model_version_id=body.model_version_id,
        slice_id=body.slice_id,
        class_mapping_id=body.class_mapping_id,
        compute_target_id=body.compute_target_id,
        attacks=attacks,
        limit=body.limit,
    )
    return ExperimentClone(config=config, warnings=[], notes=_slice_notes(protocol, images))


# ---------------------------------------------------------------- nâng lên chính thức


def promote(session: Session, experiment_id: UUID, protocol_id: UUID) -> ExperimentClone:
    """`POST /experiments/{id}/promote`: bản nháp Chính thức từ experiment Khám phá đã kết thúc.

    Giữ model, slice, class mapping, compute target và giới hạn của nguồn. Attack là các attack
    bắt buộc của protocol (level bắt buộc hợp level nguồn đã chạy cho cùng spec), cộng các attack
    nguồn mà protocol không yêu cầu. Spec nguồn đã ngừng hoạt động lên version hiện hành như khi
    nhân bản (kèm `warnings`). Không kế thừa run hay kết quả nào của nguồn."""
    source = session.get(m.Experiment, experiment_id)
    if source is None:
        raise NotFound("Không có experiment này")
    source_protocol = session.get(m.Protocol, source.protocol_id)
    assert source_protocol is not None  # khóa ngoại không null
    if source_protocol.status != ProtocolStatus.DEV:
        raise Conflict("Chỉ nâng được experiment Khám phá lên chính thức")
    if source.status not in FINISHED:
        raise Conflict(
            f"Experiment đang ở trạng thái {source.status}; chờ experiment kết thúc rồi nâng lên"
        )
    protocol = session.get(m.Protocol, protocol_id)
    if protocol is None:
        raise NotFound("Không có protocol này")
    if protocol.status != ProtocolStatus.ACTIVE:
        raise Conflict(
            f"Protocol {protocol.name} v{protocol.version} đang ở trạng thái {protocol.status};"
            " chỉ nâng lên protocol active"
        )

    images = len(_slice(session, source.slice_id).image_ids)
    base = experiment_views.clone(session, experiment_id)
    by_name: dict[str, AttackConfig] = {}
    for attack in base.config.attacks:
        row = session.get(m.AttackSpecRow, attack.attack_spec_id)
        assert row is not None  # experiment chỉ tạo được với spec trong catalog
        by_name[row.name] = attack
    attacks: list[AttackConfig] = []
    for required in ProtocolBody.model_validate(protocol.body).required_attacks:
        row = _spec_by_sha(session, required.spec_sha256)
        if row is None:
            raise Conflict(
                f"Không có {required.attack_spec_name} đúng version protocol yêu cầu trong catalog"
            )
        source_attack = by_name.pop(required.attack_spec_name, None)
        attacks.append(
            _required_config(
                required,
                row,
                extra_levels=(
                    source_attack.grid.levels
                    if source_attack is not None and source_attack.grid is not None
                    else []
                ),
                seed=source_attack.seed if source_attack is not None else DEFAULT_SEED,
                training_slice_id=(
                    source_attack.training_slice_id if source_attack is not None else None
                ),
                images=images,
            )
        )
    attacks.extend(by_name.values())  # attack nguồn mà protocol không yêu cầu, giữ thứ tự nguồn
    config = ExperimentCreate.model_validate(
        {
            **base.config.model_dump(mode="json"),
            "protocol_id": str(protocol.id),
            "attacks": [a.model_dump(mode="json") for a in attacks],
            "cloned_from": None,
            "promoted_from": str(source.id),
        }
    )
    kept = {a.attack_spec_id for a in attacks}
    return ExperimentClone(
        config=config,
        warnings=[w for w in base.warnings if w.attack_spec_id in kept],
        notes=_slice_notes(protocol, images),
    )


def _slice(session: Session, slice_id: UUID) -> m.Slice:
    row = session.get(m.Slice, slice_id)
    assert row is not None  # khóa ngoại của experiment
    return row
