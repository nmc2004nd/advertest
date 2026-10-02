"""Dữ liệu review đọc từ DB (plan task 11, 13, 15, 16): case bắt buộc, run cần giải trình, điều
kiện gửi duyệt, danh sách kiểm tra, tiêu chí và `ReviewView` trong `ExperimentDetail`.

Không import `experiment_views` (nó import module này)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from advertest_contracts.enums import (
    ChecklistCode,
    DisplayMode,
    ExperimentStatus,
    ProtocolStatus,
    ReviewDecision,
    RunStatus,
    SubmitCheckCode,
)
from advertest_contracts.models import (
    AttackSpec,
    CaseVerdictView,
    ChecklistItem,
    ComplianceItem,
    CriterionResult,
    ExperimentConfig,
    ProtocolBody,
    RequiredCase,
    ReviewView,
    RunExplanation,
    RunMetrics,
    SearchResult,
    SubmitCheckItem,
    UserRef,
)
from backend.app.db import models as m
from backend.app.protocols import compliance
from backend.app.reviews.criteria import RunPoint, evaluate
from backend.app.services import artifacts, searches
from backend.app.services.experiment_config import spec_of

OPEN = (ExperimentStatus.SUBMITTED_FOR_REVIEW, ExperimentStatus.IN_REVIEW)
DECIDED = {
    ReviewDecision.APPROVE: ExperimentStatus.APPROVED,
    ReviewDecision.CHANGES_REQUESTED: ExperimentStatus.CHANGES_REQUESTED,
    ReviewDecision.REJECT: ExperimentStatus.REJECTED,
}
REVIEW_STATUSES = (*OPEN, *DECIDED.values())
TERMINAL = (
    RunStatus.COMPLETED,
    RunStatus.FAILED,
    RunStatus.SKIPPED,
    RunStatus.STOPPED_LIMIT,
    RunStatus.CANCELLED,
)
# Run bỏ qua không cần giải trình (requirements.md Phase 8, Gửi duyệt).
NO_EXPLANATION_SKIPS = ("cached", "early_stop")


def user_ref(session: Session, user_id: UUID) -> UserRef:
    user = session.get(m.User, user_id)
    assert user is not None  # khóa ngoại
    return UserRef(id=user.id, full_name=user.full_name)


@dataclass
class Context:
    """Experiment kèm protocol, cấu hình, spec và run đã nạp."""

    experiment: m.Experiment
    protocol: m.Protocol
    body: ProtocolBody | None  # None với protocol dev
    config: ExperimentConfig
    specs: dict[UUID, AttackSpec]
    runs: list[m.Run]

    @property
    def is_dev(self) -> bool:
        return self.protocol.status == ProtocolStatus.DEV

    def required_ids(self) -> dict[str, UUID]:
        """Tên attack bắt buộc → attack_spec_id trong cấu hình (bỏ attack vắng mặt)."""
        if self.body is None:
            return {}
        by_name = {self.specs[a.attack_spec_id].name: a.attack_spec_id for a in self.config.attacks}
        return {
            r.attack_spec_name: by_name[r.attack_spec_name]
            for r in self.body.required_attacks
            if r.attack_spec_name in by_name
        }


def load(session: Session, experiment: m.Experiment) -> Context:
    protocol = session.get(m.Protocol, experiment.protocol_id)
    assert protocol is not None  # khóa ngoại
    config = ExperimentConfig.model_validate(experiment.config)
    ids = {a.attack_spec_id for a in config.attacks}
    rows = session.scalars(select(m.AttackSpecRow).where(m.AttackSpecRow.id.in_(ids)))
    runs = list(
        session.scalars(
            select(m.Run).where(m.Run.experiment_id == experiment.id).order_by(m.Run.ordinal)
        )
    )
    body = (
        None
        if protocol.status == ProtocolStatus.DEV
        else ProtocolBody.model_validate(protocol.body)
    )
    return Context(experiment, protocol, body, config, {r.id: spec_of(r) for r in rows}, runs)


# ---------------------------------------------------------------- gửi duyệt


def _reason_code(run: m.Run) -> str | None:
    return (run.status_reason or {}).get("code")


def runs_requiring_explanation(ctx: Context) -> list[m.Run]:
    """Run của attack bắt buộc không `completed`, trừ `skipped` do `cached`/`early_stop`."""
    required = set(ctx.required_ids().values())
    return [
        run
        for run in ctx.runs
        if run.attack_spec_id in required
        and run.status != RunStatus.COMPLETED
        and not (run.status == RunStatus.SKIPPED and _reason_code(run) in NO_EXPLANATION_SKIPS)
    ]


def compliance_items(session: Session, ctx: Context) -> list[ComplianceItem]:
    model = session.get(m.ModelVersion, ctx.experiment.model_version_id)
    slice_row = session.get(m.Slice, ctx.experiment.slice_id)
    assert model is not None and slice_row is not None  # khóa ngoại
    return compliance.evaluate(
        session,
        protocol=ctx.protocol,
        attacks=[(a, ctx.specs[a.attack_spec_id]) for a in ctx.config.attacks],
        slice_size=len(slice_row.image_ids),
        supports_gradients=model.supports_gradients,
        for_creation=False,
    )


def submit_check(session: Session, ctx: Context) -> list[SubmitCheckItem]:
    """Điều kiện gửi duyệt (409 khi không thỏa); lời giải trình (422) nằm ở
    `runs_requiring_explanation`."""
    C = SubmitCheckCode
    status = ctx.experiment.status
    items = [
        SubmitCheckItem(
            code=C.EXPERIMENT_COMPLETED,
            satisfied=status == ExperimentStatus.COMPLETED,
            detail="Đã hoàn thành" if status == ExperimentStatus.COMPLETED else f"Đang {status}",
        ),
        SubmitCheckItem(
            code=C.PROTOCOL_NOT_DEV,
            satisfied=not ctx.is_dev,
            detail=f"Protocol {ctx.protocol.name} v{ctx.protocol.version}"
            + (" (phát triển) không gửi duyệt được" if ctx.is_dev else ""),
        ),
    ]
    if ctx.body is None:
        return items
    required = set(ctx.required_ids().values())
    pending = [r for r in ctx.runs if r.attack_spec_id in required and r.status not in TERMINAL]
    items.append(
        SubmitCheckItem(
            code=C.RUNS_FINAL,
            satisfied=not pending,
            detail="Mọi run bắt buộc có trạng thái cuối"
            if not pending
            else f"{len(pending)} run bắt buộc chưa kết thúc",
        )
    )
    dirty = [r for r in ctx.runs if r.git_dirty]
    if ctx.body.forbid_dirty_runs:
        detail = (
            "Không run nào chạy từ code chưa commit"
            if not dirty
            else f"{len(dirty)} run chạy từ code chưa commit (protocol cấm)"
        )
        items.append(SubmitCheckItem(code=C.NO_DIRTY_RUNS, satisfied=not dirty, detail=detail))
    else:
        items.append(
            SubmitCheckItem(
                code=C.NO_DIRTY_RUNS,
                satisfied=True,
                detail=f"Protocol cho phép code chưa commit ({len(dirty)} run)",
            )
        )
    hidden = [c for c in required_cases(session, ctx) if c.display_mode != DisplayMode.NORMAL]
    items.append(
        SubmitCheckItem(
            code=C.REQUIRED_CASES_VISIBLE,
            satisfied=not hidden,
            detail="Mọi case bắt buộc đã làm mờ"
            if not hidden
            else f"{len(hidden)} case bắt buộc chưa làm mờ (dữ liệu trước Phase 6)",
        )
    )
    return items


# ---------------------------------------------------------------- case bắt buộc, verdict


def current_verdicts(session: Session, case_ids: list[UUID]) -> dict[UUID, CaseVerdictView]:
    if not case_ids:
        return {}
    latest = (
        select(m.CaseVerdict.failure_case_id, func.max(m.CaseVerdict.version).label("v"))
        .where(m.CaseVerdict.failure_case_id.in_(case_ids))
        .group_by(m.CaseVerdict.failure_case_id)
        .subquery()
    )
    rows = session.scalars(
        select(m.CaseVerdict).join(
            latest,
            (latest.c.failure_case_id == m.CaseVerdict.failure_case_id)
            & (latest.c.v == m.CaseVerdict.version),
        )
    )
    return {row.failure_case_id: verdict_view(session, row) for row in rows}


def verdict_view(session: Session, row: m.CaseVerdict) -> CaseVerdictView:
    return CaseVerdictView(
        failure_case_id=row.failure_case_id,
        version=row.version,
        reviewer=user_ref(session, row.reviewer_id),
        severity=row.severity,
        kind=row.kind,
        mitigation=row.mitigation,
        created_at=row.created_at,
    )


def required_cases(session: Session, ctx: Context) -> list[RequiredCase]:
    """Top `cases_to_review_per_attack` theo `severity_score` của mỗi attack bắt buộc trên mọi
    run của attack đó; cùng điểm theo `image_id`, rồi id (xác định)."""
    if ctx.body is None:
        return []
    limit = ctx.body.cases_to_review_per_attack
    runs = {run.id: run for run in ctx.runs}
    dataset_mode = artifacts.display_mode(session, ctx.runs[0]) if ctx.runs else None
    picked: list[tuple[str, m.FailureCase]] = []
    for name, spec_id in ctx.required_ids().items():
        run_ids = [r.id for r in ctx.runs if r.attack_spec_id == spec_id]
        if not run_ids:
            continue
        cases = session.scalars(
            select(m.FailureCase)
            .where(m.FailureCase.run_id.in_(run_ids))
            .order_by(m.FailureCase.severity_score.desc(), m.FailureCase.image_id, m.FailureCase.id)
            .limit(limit)
        )
        picked.extend((name, case) for case in cases)
    verdicts = current_verdicts(session, [case.id for _, case in picked])
    out = []
    for name, case in picked:
        assert dataset_mode is not None  # có case thì có run
        out.append(
            RequiredCase(
                failure_case_id=case.id,
                run_id=case.run_id,
                attack_spec_name=name,
                level=runs[case.run_id].level,
                image_id=case.image_id,
                severity_score=case.severity_score,
                display_mode=artifacts.case_mode(case, dataset_mode),
                current_verdict=verdicts.get(case.id),
            )
        )
    return out


# ---------------------------------------------------------------- tiêu chí, checklist


def _point(run: m.Run) -> RunPoint:
    reason = run.status_reason or {}
    trigger = reason.get("trigger_run_id")
    return RunPoint(
        run_id=run.id,
        level=run.level,
        status=run.status,
        reason_code=reason.get("code"),
        trigger_run_id=UUID(trigger) if trigger else None,
        metrics=RunMetrics.model_validate(run.metrics) if run.metrics else None,
    )


def criteria_results(session: Session, ctx: Context) -> list[CriterionResult]:
    if ctx.body is None:
        return []
    full = [run for run in ctx.runs if run.scope == "full"]
    by_id = {run.id: _point(run) for run in full}
    grid: dict[str, list[RunPoint]] = defaultdict(list)
    for run in full:
        grid[ctx.specs[run.attack_spec_id].name].append(by_id[run.id])
    found: dict[str, SearchResult] = {
        ctx.specs[r.attack_spec_id].name: r
        for r in searches.results(session, ctx.experiment.id)
        if r.attack_spec_id in ctx.specs
    }
    return evaluate(ctx.body, grid, by_id, found)


def checklist(ctx: Context, cases: list[RequiredCase]) -> list[ChecklistItem]:
    """Chỉ điều kiện trạng thái phía server (kickoff Phase 8)."""
    reviewed = sum(1 for case in cases if case.current_verdict is not None)
    return [
        ChecklistItem(
            code=ChecklistCode.PROTOCOL_NOT_DEV,
            satisfied=not ctx.is_dev,
            detail=f"Protocol {ctx.protocol.name} v{ctx.protocol.version}",
        ),
        ChecklistItem(
            code=ChecklistCode.REQUIRED_CASES_REVIEWED,
            satisfied=reviewed == len(cases),
            detail=f"{reviewed}/{len(cases)} case bắt buộc đã có verdict",
        ),
    ]


# ---------------------------------------------------------------- ReviewView


def latest_review(session: Session, experiment_id: UUID) -> m.Review | None:
    return session.scalar(
        select(m.Review)
        .where(m.Review.experiment_id == experiment_id)
        .order_by(m.Review.version.desc())
        .limit(1)
    )


def explanations(session: Session, ctx: Context) -> list[RunExplanation]:
    run_ids = [run.id for run in ctx.runs]
    if not run_ids:
        return []
    rows = session.scalars(
        select(m.RunExplanation)
        .where(m.RunExplanation.run_id.in_(run_ids))
        .order_by(m.RunExplanation.created_at, m.RunExplanation.run_id)
    )
    return [
        RunExplanation(
            run_id=row.run_id,
            author=user_ref(session, row.author_id),
            text=row.text,
            created_at=row.created_at,
        )
        for row in rows
    ]


def comments_count(session: Session, experiment_id: UUID) -> int:
    return (
        session.scalar(
            select(func.count())
            .select_from(m.ReviewComment)
            .where(m.ReviewComment.experiment_id == experiment_id)
        )
        or 0
    )


def review_view(session: Session, ctx: Context) -> ReviewView | None:
    experiment = ctx.experiment
    if experiment.status not in REVIEW_STATUSES:
        return None
    assert experiment.review_submitted_at is not None  # đặt khi gửi duyệt
    cases = required_cases(session, ctx)
    decided = experiment.status in DECIDED.values()
    review = latest_review(session, experiment.id) if decided else None
    if review is not None:
        criteria = [CriterionResult.model_validate(c) for c in review.criteria_results]
        items = [ChecklistItem.model_validate(c) for c in review.checklist]
    else:
        criteria = criteria_results(session, ctx)
        items = checklist(ctx, cases)
    assignee = experiment.review_assignee_id
    return ReviewView(
        submitted_at=experiment.review_submitted_at,
        submission_note=experiment.submission_note,
        run_explanations=explanations(session, ctx),
        assignee=user_ref(session, assignee) if assignee is not None else None,
        claimed_at=experiment.claimed_at,
        decision=review.decision if review else None,
        decided_at=experiment.decided_at if review else None,
        model_verdict=review.model_verdict if review else None,
        conclusion=review.conclusion if review else None,
        mitigation=review.mitigation if review else None,
        inconclusive_justification=review.inconclusive_justification if review else None,
        criteria_results=criteria,
        checklist=items,
        required_cases=cases,
        comments_count=comments_count(session, experiment.id),
    )
