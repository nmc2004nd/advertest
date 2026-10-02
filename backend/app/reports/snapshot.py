"""Dựng `ReportSnapshot` từ DB và MinIO (requirements.md Phase 8, mục Report; plan task 19).

Snapshot là toàn bộ nội dung report; file JSON là `canonical_json(snapshot)`. Mọi danh sách có
thứ tự xác định (theo `ordinal`, level, thời gian, id) để cùng dữ liệu cho cùng snapshot.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from advertest_contracts.enums import (
    AttackKind,
    EvalScope,
    ExperimentStatus,
    ProtocolStatus,
    ReportNoteCode,
    RunMode,
    SearchStage,
)
from advertest_contracts.models import (
    CaseAnonymization,
    CaseVerdictView,
    ComputeTargetRef,
    CriterionResult,
    Limit,
    Manifest,
    ProtocolRef,
    ReportNote,
    ReportSnapshot,
    RunMetrics,
    StatusReason,
)
from backend.app.db import models as m
from backend.app.reviews.views import current_verdicts, load, required_cases, user_ref
from backend.app.services import experiment_views, searches
from ml_core.store import KeyNotFoundError

Reader = Callable[[str], bytes]
ARTIFACTS_URI = "s3://artifacts/"
TIMELINE = ("experiment.submitted", "review.claimed", "review.released", "review.decided")

NOTE_TEXT = {
    ReportNoteCode.TEST_ENVIRONMENT_ONLY: (
        "Kết quả chỉ có giá trị trong môi trường kiểm thử trên dữ liệu và mô phỏng; không dùng"
        " làm căn cứ triển khai thật khi chưa được validate bằng quy trình khác."
    ),
    ReportNoteCode.INPUT_SPACE: (
        "eps và mức corruption tính trên ảnh đầu vào của model (letterbox 640 x 640, dạng float"
        " trong [0, 1], không lượng tử hóa 8-bit)."
    ),
    ReportNoteCode.OCCLUSION_STRESS: (
        "Occlusion là phép thử chịu tải (che theo tỷ lệ bounding box), không mô phỏng vật che"
        " khuất thật."
    ),
    ReportNoteCode.PATCH_FIXED_POSITION: "Patch adversarial đặt ở vị trí cố định trên ảnh.",
}


def _anonymization_note(method: str, version: int) -> str:
    detail = " (theo bounding box, không dùng model phát hiện mặt)" if method == "rule_v1" else ""
    return (
        f"Mặt người và biển số được làm mờ ở tầng hiển thị bằng {method} v{version}{detail};"
        " dữ liệu đưa vào model không đổi."
    )


def _manifest(read: Reader, run: m.Run) -> Manifest | None:
    uri = run.manifest_uri
    if uri is None or not uri.startswith(ARTIFACTS_URI):
        return None
    try:
        return Manifest.model_validate_json(read(uri.removeprefix(ARTIFACTS_URI)))
    except (KeyNotFoundError, ValidationError):
        # Manifest thiếu hay sai schema: mục tái lập ghi null (fingerprint, git_dirty lấy từ DB).
        return None


def build(session: Session, read: Reader, report: m.Report) -> ReportSnapshot:
    """`read` đọc một khóa trong bucket artifacts (manifest)."""
    experiment = session.get(m.Experiment, report.experiment_id)
    assert experiment is not None  # khóa ngoại
    if experiment.status != ExperimentStatus.APPROVED:
        raise ValueError("Report chỉ sinh cho experiment đã được chấp nhận")
    ctx = load(session, experiment)
    assert ctx.body is not None  # experiment được duyệt không gắn protocol dev
    review = session.scalar(
        select(m.Review)
        .where(m.Review.experiment_id == experiment.id)
        .order_by(m.Review.version.desc())
        .limit(1)
    )
    assert review is not None and review.model_verdict is not None and review.mitigation
    approved_at = experiment.decided_at
    assert approved_at is not None
    detail = experiment_views.detail(session, experiment.id)
    spec_by_id = ctx.specs
    required_names = {r.attack_spec_name for r in ctx.body.required_attacks}

    # ------------------------------------------------------------ cấu hình
    model = session.get(m.ModelVersion, experiment.model_version_id)
    slice_row = session.get(m.Slice, experiment.slice_id)
    mapping = session.get(m.ClassMapping, experiment.class_mapping_id)
    target = session.get(m.ComputeTarget, experiment.compute_target_id)
    assert model and slice_row and mapping and target
    model_row = session.get(m.Model, model.model_id)
    dataset_version = session.get(m.DatasetVersion, slice_row.dataset_version_id)
    assert model_row and dataset_version
    dataset = session.get(m.Dataset, dataset_version.dataset_id)
    assert dataset is not None
    excluded = sorted(k for k, v in mapping.mapping.get("classes", {}).items() if v is None)
    runs = ctx.runs
    manifests = {run.id: _manifest(read, run) for run in runs}
    gpu = next(
        (mf.environment.gpu_model for mf in manifests.values() if mf and mf.environment.gpu_model),
        target.gpu_model,
    )
    configuration = {
        "protocol": {
            "id": ctx.protocol.id,
            "name": ctx.protocol.name,
            "version": ctx.protocol.version,
            "body_sha256": ctx.protocol.body_sha256,
            "body": ctx.body.model_dump(mode="json"),
        },
        "model": {"id": model.id, "name": model_row.name, "weights_sha256": model.weights_sha256},
        "dataset_version": {
            "id": dataset_version.id,
            "dataset_name": dataset.name,
            "manifest_sha256": dataset_version.manifest_sha256,
            "anonymized": dataset.anonymized,
        },
        "slice": {
            "id": slice_row.id,
            "name": slice_row.name,
            "slice_sha256": slice_row.slice_sha256,
            "size": len(slice_row.image_ids),
        },
        "class_mapping": {
            "id": mapping.id,
            "mapping_sha256": mapping.mapping_sha256,
            "excluded_classes": excluded,
        },
        "attack_specs": [
            {
                "id": spec.id,
                "name": spec.name,
                "version": spec.version,
                "kind": spec.kind,
                "spec_sha256": spec.spec_sha256,
                "param_name": spec.primary_param.name,
                "param_unit": spec.primary_param.unit,
                "requires_training": spec.requires_training,
                "required": spec.name in required_names,
            }
            for spec in (spec_by_id[a.attack_spec_id] for a in ctx.config.attacks)
        ],
        "compute_target": ComputeTargetRef(id=target.id, name=target.name, kind=target.kind),
        "gpu_model": gpu,
        "config_sha256": experiment.config_sha256,
    }

    # ------------------------------------------------------------ kết quả
    grid = []
    for attack in ctx.config.attacks:
        if attack.mode != RunMode.GRID:
            continue
        spec = spec_by_id[attack.attack_spec_id]
        points = []
        for run in sorted(
            (r for r in runs if r.attack_spec_id == spec.id and r.scope == EvalScope.FULL),
            key=lambda r: (r.level, r.ordinal),
        ):
            metrics = RunMetrics.model_validate(run.metrics) if run.metrics else None
            reason = run.status_reason or {}
            trigger = reason.get("trigger_run_id") if reason.get("code") == "early_stop" else None
            points.append(
                {
                    "level": run.level,
                    "run_id": run.id,
                    "status": run.status,
                    "map50": metrics.attacked.map50 if metrics else None,
                    "relative_drop": metrics.relative_drop if metrics else None,
                    "attack_success_rate": metrics.attack_success_rate if metrics else None,
                    "early_stop_from_run_id": trigger,
                }
            )
        grid.append({"attack_spec_id": spec.id, "attack_spec_name": spec.name, "points": points})
    final_searches = [
        r for r in searches.results(session, experiment.id) if r.stage == SearchStage.DONE
    ]
    results = {
        "clean_metrics": detail.clean_metrics,
        "grid": grid,
        "attack_ranking": detail.attack_ranking,
        "searches": final_searches,
        "criteria": [CriterionResult.model_validate(c) for c in review.criteria_results],
    }

    # ------------------------------------------------------------ run, tái lập
    explanations = {
        row.run_id: row.text
        for row in session.scalars(
            select(m.RunExplanation).where(m.RunExplanation.run_id.in_([r.id for r in runs]))
        )
    }
    report_runs = []
    reproducibility = []
    for run in runs:
        spec = spec_by_id[run.attack_spec_id]
        report_runs.append(
            {
                "run_id": run.id,
                "attack_spec_id": spec.id,
                "attack_spec_name": spec.name,
                "level": run.level,
                "scope": run.scope,
                "search_order": run.search_order,
                "status": run.status,
                "status_reason": StatusReason.model_validate(run.status_reason)
                if run.status_reason
                else None,
                "metrics": RunMetrics.model_validate(run.metrics) if run.metrics else None,
                "processing_seconds": run.gpu_seconds,
                "explanation": explanations.get(run.id),
            }
        )
        mf = manifests[run.id]
        inputs = mf.fingerprint_inputs if mf is not None else None
        reproducibility.append(
            {
                "run_id": run.id,
                "fingerprint": run.fingerprint,
                "git_commit": inputs.git_commit if inputs else None,
                "git_dirty": inputs.git_dirty if inputs else run.git_dirty,
                "lib_versions": inputs.lib_versions if inputs else None,
                "docker_image_digest": inputs.docker_image_digest if inputs else None,
                "cached_from_run_id": run.cached_from_run_id,
            }
        )

    # ------------------------------------------------------------ case đã review
    required = {c.failure_case_id for c in required_cases(session, ctx)}
    reviewed_ids = list(
        session.scalars(
            select(m.CaseVerdict.failure_case_id)
            .join(m.FailureCase, m.FailureCase.id == m.CaseVerdict.failure_case_id)
            .join(m.Run, m.Run.id == m.FailureCase.run_id)
            .where(m.Run.experiment_id == experiment.id)
            .distinct()
        )
    )
    verdicts: dict[UUID, CaseVerdictView] = current_verdicts(session, reviewed_ids)
    run_by_id = {run.id: run for run in runs}
    cases = []
    methods: set[tuple[str, int]] = set()
    for case in sorted(
        (c for c in (session.get(m.FailureCase, cid) for cid in reviewed_ids) if c is not None),
        key=lambda c: (-c.severity_score, c.image_id, str(c.id)),
    ):
        anonymization = (
            CaseAnonymization.model_validate(case.anonymization) if case.anonymization else None
        )
        if anonymization is None or not anonymization.applied:
            continue  # report chỉ có ảnh đã làm mờ (nguyên tắc 9)
        methods.add((anonymization.method, anonymization.version))
        artifacts = case.artifacts
        run = run_by_id[case.run_id]
        cases.append(
            {
                "failure_case_id": case.id,
                "run_id": case.run_id,
                "attack_spec_name": spec_by_id[run.attack_spec_id].name,
                "level": run.level,
                "image_id": case.image_id,
                "severity_score": case.severity_score,
                "lost_objects": case.lost_objects,
                "new_false_positives": case.new_false_positives,
                "required": case.id in required,
                "anonymization": anonymization,
                "thumbnail_key": artifacts.get("adversarial_thumb") or artifacts["adversarial_png"],
                "verdict": verdicts[case.id],
            }
        )

    # ------------------------------------------------------------ lịch sử
    history = {
        "related_experiments": _related(session, experiment, ctx.protocol, approved_at),
        "timeline": [
            {"action": row.action, "actor": user_ref(session, row.actor_id), "at": row.created_at}
            for row in session.scalars(
                select(m.AuditLog)
                .where(
                    m.AuditLog.entity_id == experiment.id,
                    m.AuditLog.action.in_(TIMELINE),
                    m.AuditLog.actor_id.is_not(None),
                )
                .order_by(m.AuditLog.created_at, m.AuditLog.id)
            )
            if row.actor_id is not None
        ],
        "comments_count": detail.review.comments_count if detail.review else 0,
    }

    # ------------------------------------------------------------ lưu ý
    notes = [
        ReportNote(
            code=ReportNoteCode.TEST_ENVIRONMENT_ONLY,
            text=NOTE_TEXT[ReportNoteCode.TEST_ENVIRONMENT_ONLY],
        ),
        ReportNote(code=ReportNoteCode.INPUT_SPACE, text=NOTE_TEXT[ReportNoteCode.INPUT_SPACE]),
    ]
    specs = list(spec_by_id.values())
    if any(s.kind == AttackKind.OCCLUSION for s in specs):
        notes.append(
            ReportNote(
                code=ReportNoteCode.OCCLUSION_STRESS,
                text=NOTE_TEXT[ReportNoteCode.OCCLUSION_STRESS],
            )
        )
    if any(s.requires_training for s in specs):
        notes.append(
            ReportNote(
                code=ReportNoteCode.PATCH_FIXED_POSITION,
                text=NOTE_TEXT[ReportNoteCode.PATCH_FIXED_POSITION],
            )
        )
    if cases:
        text = " ".join(_anonymization_note(*method) for method in sorted(methods))
        notes.append(ReportNote(code=ReportNoteCode.ANONYMIZATION, text=text))
    if excluded:
        notes.append(
            ReportNote(
                code=ReportNoteCode.EXCLUDED_CLASSES,
                text="Class bị loại khỏi metric (không map được sang class của model): "
                + ", ".join(excluded)
                + ".",
            )
        )
    dirty = sum(1 for r in reproducibility if r["git_dirty"])
    if dirty:
        notes.append(
            ReportNote(
                code=ReportNoteCode.GIT_DIRTY,
                text=f"{dirty} run chạy từ code chưa commit (protocol cho phép); kết quả có thể"
                " không tái lập được.",
            )
        )

    owner = user_ref(session, experiment.created_by)
    return ReportSnapshot.model_validate(
        {
            "report_id": report.id,
            "summary": {
                "experiment_id": experiment.id,
                "experiment_name": experiment.name,
                "owner": owner,
                "model_verdict": review.model_verdict,
                "conclusion": review.conclusion,
                "mitigation": review.mitigation,
                "inconclusive_justification": review.inconclusive_justification,
                "approved_by": user_ref(session, review.reviewer_id),
                "approved_at": approved_at,
            },
            "notes": notes,
            "configuration": configuration,
            "results": results,
            "runs": report_runs,
            "reviewed_cases": cases,
            "history": history,
            "reproducibility": reproducibility,
            "resources": {
                "processing_seconds_used": float(experiment.processing_seconds_used),
                "limit": Limit(kind=experiment.limit_kind, value=experiment.limit_value),
            },
        }
    )


def _related(
    session: Session, experiment: m.Experiment, protocol: m.Protocol, approved_at: datetime
) -> list[dict[str, object]]:
    """Experiment khác cùng model version và dataset version, gắn protocol này (mọi version)
    hoặc protocol dev, tạo trước thời điểm duyệt (kickoff Phase 8)."""
    slice_row = session.get(m.Slice, experiment.slice_id)
    assert slice_row is not None
    rows = session.execute(
        select(m.Experiment, m.Protocol)
        .join(m.Protocol, m.Protocol.id == m.Experiment.protocol_id)
        .join(m.Slice, m.Slice.id == m.Experiment.slice_id)
        .where(
            m.Experiment.id != experiment.id,
            m.Experiment.model_version_id == experiment.model_version_id,
            m.Slice.dataset_version_id == slice_row.dataset_version_id,
            or_(m.Protocol.name == protocol.name, m.Protocol.status == ProtocolStatus.DEV),
            m.Experiment.created_at < approved_at,
        )
        .order_by(m.Experiment.created_at, m.Experiment.id)
    )
    return [
        {
            "id": other.id,
            "name": other.name,
            "status": other.status,
            "owner": user_ref(session, other.created_by),
            "protocol": ProtocolRef(id=p.id, name=p.name, status=p.status),
            "protocol_version": p.version,
            "dev": p.status == ProtocolStatus.DEV,
            "created_at": other.created_at,
        }
        for other, p in rows
    ]
