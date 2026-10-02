"""Gửi duyệt, nhận review, verdict, quyết định, bình luận (requirements.md Phase 8; plan task
11-18). Mọi thao tác khóa dòng experiment trước (`FOR UPDATE`) nên hai request đồng thời được
xếp hàng; trigger DB (0009) chặn thêm một lớp."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from advertest_contracts.enums import (
    CommentTargetType,
    CriterionStatus,
    ErrorCode,
    ExperimentStatus,
    ReviewDecision,
    ReviewQueueFilter,
)
from advertest_contracts.models import (
    CaseVerdictInput,
    CaseVerdictView,
    FieldError,
    ProtocolRef,
    ReviewComment,
    ReviewCommentCreate,
    ReviewDecisionInput,
    ReviewQueueItem,
    RunMetrics,
    SubmitForReview,
)
from backend.app.db import models as m
from backend.app.reviews import emails
from backend.app.reviews.lock import ensure_unlocked
from backend.app.reviews.views import (
    DECIDED,
    OPEN,
    checklist,
    compliance_items,
    criteria_results,
    load,
    required_cases,
    runs_requiring_explanation,
    submit_check,
    user_ref,
    verdict_view,
)
from backend.app.services import audit, experiment_views
from backend.app.services.errors import (
    ChecklistIncomplete,
    Conflict,
    Forbidden,
    InvalidConfig,
    NotFound,
)

Sort = Literal["submitted_at", "max_drop"]
ENTITY = "experiment"


def _locked_experiment(session: Session, experiment_id: UUID) -> m.Experiment:
    experiment = session.get(m.Experiment, experiment_id, with_for_update=True)
    if experiment is None:
        raise NotFound("Không có experiment này")
    return experiment


# ---------------------------------------------------------------- gửi duyệt (task 11)


def submit(
    session: Session, *, actor: m.User, experiment_id: UUID, body: SubmitForReview, now: datetime
) -> None:
    experiment = _locked_experiment(session, experiment_id)
    if experiment.created_by != actor.id:
        raise Forbidden("Chỉ người tạo experiment mới gửi duyệt được")
    ensure_unlocked(experiment)
    ctx = load(session, experiment)
    failed = [item for item in submit_check(session, ctx) if not item.satisfied]
    if failed:
        raise Conflict("Chưa đủ điều kiện gửi duyệt: " + "; ".join(i.detail for i in failed))
    if not all(item.satisfied for item in compliance_items(session, ctx)):
        raise Conflict("Experiment không còn tuân thủ protocol đã gắn")
    needed = {run.id for run in runs_requiring_explanation(ctx)}
    given = set(body.run_explanations)
    errors = [
        FieldError(path=f"run_explanations.{run_id}", message="Run bắt buộc này cần lời giải trình")
        for run_id in sorted(needed - given, key=str)
    ] + [
        FieldError(
            path=f"run_explanations.{run_id}",
            message="Run này không cần giải trình (không phải run bắt buộc chưa hoàn thành)",
        )
        for run_id in sorted(given - needed, key=str)
    ]
    if errors:
        raise InvalidConfig(
            f"Lời giải trình chưa đúng ({len(errors)} lỗi)", errors, ErrorCode.INVALID_REQUEST
        )
    experiment.status = ExperimentStatus.SUBMITTED_FOR_REVIEW
    experiment.locked_at = now
    experiment.review_submitted_at = now
    experiment.submission_note = body.note
    for run_id, text in body.run_explanations.items():
        session.add(m.RunExplanation(run_id=run_id, author_id=actor.id, text=text))
        audit.record(
            session,
            actor=actor,
            action="run_explanation.added",
            entity_type="run",
            entity_id=run_id,
            after={"experiment_id": str(experiment.id)},
        )
    audit.record(
        session,
        actor=actor,
        action="experiment.submitted",
        entity_type=ENTITY,
        entity_id=experiment.id,
        before={"status": ExperimentStatus.COMPLETED.value},
        after={
            "status": ExperimentStatus.SUBMITTED_FOR_REVIEW.value,
            "explanations": len(body.run_explanations),
        },
    )
    emails.submitted(session, experiment, ctx.protocol)
    session.flush()


# ---------------------------------------------------------------- nhận review (task 12)


def claim(session: Session, *, actor: m.User, experiment_id: UUID, now: datetime) -> None:
    experiment = _locked_experiment(session, experiment_id)
    if experiment.created_by == actor.id:
        raise Forbidden("Không được review experiment do chính mình tạo")
    if experiment.status != ExperimentStatus.SUBMITTED_FOR_REVIEW:
        raise Conflict(f"Experiment đang ở trạng thái {experiment.status}, không nhận được")
    experiment.status = ExperimentStatus.IN_REVIEW
    experiment.review_assignee_id = actor.id
    experiment.claimed_at = now
    audit.record(
        session,
        actor=actor,
        action="review.claimed",
        entity_type=ENTITY,
        entity_id=experiment.id,
        after={"assignee_id": str(actor.id)},
    )
    session.flush()


def release(session: Session, *, actor: m.User, experiment_id: UUID) -> None:
    experiment = _locked_experiment(session, experiment_id)
    if experiment.status != ExperimentStatus.IN_REVIEW:
        raise Conflict(f"Experiment đang ở trạng thái {experiment.status}, không trả lại được")
    if experiment.review_assignee_id != actor.id:
        raise Forbidden("Chỉ người đang nhận review mới trả lại được")
    experiment.status = ExperimentStatus.SUBMITTED_FOR_REVIEW
    experiment.review_assignee_id = None
    experiment.claimed_at = None
    audit.record(
        session,
        actor=actor,
        action="review.released",
        entity_type=ENTITY,
        entity_id=experiment.id,
        before={"assignee_id": str(actor.id)},
    )
    session.flush()


def _require_assignee(experiment: m.Experiment, actor: m.User) -> None:
    """Đã quyết định → 409; không phải người đang nhận (hoặc là người tạo) → 403."""
    if experiment.status in DECIDED.values():
        raise Conflict("Review đã có quyết định; không thay đổi được nữa")
    if (
        experiment.status != ExperimentStatus.IN_REVIEW
        or experiment.review_assignee_id != actor.id
        or experiment.created_by == actor.id
    ):
        raise Forbidden("Chỉ người đang nhận review mới thực hiện được")


# ---------------------------------------------------------------- verdict (task 14)


def add_verdict(
    session: Session,
    *,
    actor: m.User,
    experiment_id: UUID,
    case_id: UUID,
    body: CaseVerdictInput,
) -> CaseVerdictView:
    experiment = _locked_experiment(session, experiment_id)
    _require_assignee(experiment, actor)
    case = session.get(m.FailureCase, case_id)
    run = session.get(m.Run, case.run_id) if case is not None else None
    if case is None or run is None or run.experiment_id != experiment.id:
        raise NotFound("Không có failure case này trong experiment")
    version = (
        session.scalar(
            select(func.max(m.CaseVerdict.version)).where(m.CaseVerdict.failure_case_id == case_id)
        )
        or 0
    ) + 1
    row = m.CaseVerdict(
        failure_case_id=case_id,
        reviewer_id=actor.id,
        version=version,
        severity=body.severity,
        kind=body.kind,
        mitigation=body.mitigation,
    )
    session.add(row)
    session.flush()
    session.refresh(row)
    audit.record(
        session,
        actor=actor,
        action="case_verdict.recorded",
        entity_type="failure_case",
        entity_id=case_id,
        after={
            "experiment_id": str(experiment.id),
            "version": version,
            "severity": body.severity.value,
            "kind": body.kind.value,
        },
    )
    return verdict_view(session, row)


def list_verdicts(session: Session, case_id: UUID) -> list[CaseVerdictView]:
    if session.get(m.FailureCase, case_id) is None:
        raise NotFound("Không có failure case này")
    rows = session.scalars(
        select(m.CaseVerdict)
        .where(m.CaseVerdict.failure_case_id == case_id)
        .order_by(m.CaseVerdict.version.desc())
    )
    return [verdict_view(session, row) for row in rows]


# ---------------------------------------------------------------- quyết định (task 16)


def decide(
    session: Session,
    *,
    actor: m.User,
    experiment_id: UUID,
    body: ReviewDecisionInput,
    now: datetime,
) -> None:
    """Thứ tự (kickoff): sai người → 403; thiếu trường nhập → 422 (contract và
    `inconclusive_justification` ở đây); checklist chưa đủ → 409 `checklist_incomplete`."""
    experiment = _locked_experiment(session, experiment_id)
    _require_assignee(experiment, actor)
    ctx = load(session, experiment)
    criteria = criteria_results(session, ctx)
    cases = required_cases(session, ctx)
    items = checklist(ctx, cases)
    approve = body.decision == ReviewDecision.APPROVE
    inconclusive = any(c.status == CriterionStatus.INCONCLUSIVE for c in criteria)
    if approve and inconclusive and body.inconclusive_justification is None:
        raise InvalidConfig(
            "Có tiêu chí chưa kết luận: cần giải trình",
            [
                FieldError(
                    path="inconclusive_justification",
                    message="Bắt buộc khi có tiêu chí inconclusive",
                )
            ],
            ErrorCode.INVALID_REQUEST,
        )
    if approve and not all(item.satisfied for item in items):
        missing = [item.detail for item in items if not item.satisfied]
        raise ChecklistIncomplete("Chưa đủ điều kiện chấp nhận: " + "; ".join(missing), items)
    version = (
        session.scalar(
            select(func.max(m.Review.version)).where(m.Review.experiment_id == experiment.id)
        )
        or 0
    ) + 1
    review = m.Review(
        experiment_id=experiment.id,
        reviewer_id=actor.id,
        version=version,
        decision=body.decision,
        conclusion=body.conclusion,
        mitigation=body.mitigation,
        model_verdict=body.model_verdict,
        inconclusive_justification=body.inconclusive_justification,
        criteria_results=[c.model_dump(mode="json") for c in criteria],
        checklist=[i.model_dump(mode="json") for i in items],
    )
    session.add(review)
    before = experiment.status
    experiment.status = DECIDED[body.decision]
    experiment.decided_at = now
    session.flush()
    audit.record(
        session,
        actor=actor,
        action="review.decided",
        entity_type=ENTITY,
        entity_id=experiment.id,
        before={"status": before.value},
        after={
            "status": experiment.status.value,
            "decision": body.decision.value,
            "model_verdict": body.model_verdict.value if body.model_verdict else None,
        },
    )
    emails.decided(session, experiment, review)
    session.flush()


# ---------------------------------------------------------------- bình luận (task 17)


def _target_belongs(session: Session, experiment: m.Experiment, body: ReviewCommentCreate) -> bool:
    if body.target_type == CommentTargetType.EXPERIMENT:
        return body.target_id == experiment.id
    if body.target_type == CommentTargetType.RUN:
        run = session.get(m.Run, body.target_id)
        return run is not None and run.experiment_id == experiment.id
    case = session.get(m.FailureCase, body.target_id)
    run = session.get(m.Run, case.run_id) if case is not None else None
    return run is not None and run.experiment_id == experiment.id


def add_comment(
    session: Session, *, actor: m.User, experiment_id: UUID, body: ReviewCommentCreate
) -> ReviewComment:
    experiment = _locked_experiment(session, experiment_id)
    if experiment.status not in OPEN:
        raise Conflict(
            f"Chỉ bình luận được khi experiment đang chờ hoặc đang review ({experiment.status})"
        )
    if not _target_belongs(session, experiment, body):
        raise InvalidConfig(
            "Đối tượng bình luận không thuộc experiment",
            [FieldError(path="target_id", message="Không thuộc experiment này")],
            ErrorCode.INVALID_REQUEST,
        )
    row = m.ReviewComment(
        experiment_id=experiment.id,
        author_id=actor.id,
        target_type=body.target_type,
        target_id=body.target_id,
        body=body.body,
    )
    session.add(row)
    session.flush()
    session.refresh(row)
    audit.record(
        session,
        actor=actor,
        action="review.comment_added",
        entity_type=ENTITY,
        entity_id=experiment.id,
        after={
            "comment_id": str(row.id),
            "target_type": body.target_type.value,
            "target_id": str(body.target_id),
        },
    )
    return comment_view(session, row)


def comment_view(session: Session, row: m.ReviewComment) -> ReviewComment:
    return ReviewComment(
        id=row.id,
        experiment_id=row.experiment_id,
        author=user_ref(session, row.author_id),
        body=row.body,
        target_type=row.target_type,
        target_id=row.target_id,
        created_at=row.created_at,
    )


def list_comments(session: Session, experiment_id: UUID) -> list[ReviewComment]:
    if session.get(m.Experiment, experiment_id) is None:
        raise NotFound("Không có experiment này")
    rows = session.scalars(
        select(m.ReviewComment)
        .where(m.ReviewComment.experiment_id == experiment_id)
        .order_by(m.ReviewComment.created_at, m.ReviewComment.id)
    )
    return [comment_view(session, row) for row in rows]


# ---------------------------------------------------------------- hàng đợi (task 12)


QUEUE_STATUSES = {
    ReviewQueueFilter.WAITING: (ExperimentStatus.SUBMITTED_FOR_REVIEW,),
    ReviewQueueFilter.MINE: (ExperimentStatus.IN_REVIEW,),
    ReviewQueueFilter.DECIDED: tuple(DECIDED.values()),
}


def _max_drop(session: Session, experiment_id: UUID) -> float | None:
    # JSONB lưu None thành JSON null (không phải SQL NULL) nên lọc ở Python.
    rows: list[dict[str, object] | None] = list(
        session.scalars(
            select(m.Run.metrics).where(m.Run.experiment_id == experiment_id, m.Run.scope == "full")
        )
    )
    known = [
        drop
        for drop in (RunMetrics.model_validate(row).relative_drop for row in rows if row)
        if drop is not None
    ]
    return max(known) if known else None


def queue(
    session: Session, *, actor: m.User, status: ReviewQueueFilter, sort: Sort
) -> list[ReviewQueueItem]:
    """Không gồm experiment do người gọi tạo. `mine`: đang review do người gọi nhận; `decided`:
    mọi experiment đã quyết định (người dùng chốt ở kế hoạch Group 2)."""
    query = select(m.Experiment).where(
        m.Experiment.status.in_(QUEUE_STATUSES[status]), m.Experiment.created_by != actor.id
    )
    if status == ReviewQueueFilter.MINE:
        query = query.where(m.Experiment.review_assignee_id == actor.id)
    experiments = list(session.scalars(query))
    summaries = experiment_views.summaries(session, [e.id for e in experiments])
    items: list[ReviewQueueItem] = []
    for experiment in experiments:
        ctx = load(session, experiment)
        cases = required_cases(session, ctx)
        review = (
            session.scalar(
                select(m.Review.decision)
                .where(m.Review.experiment_id == experiment.id)
                .order_by(m.Review.version.desc())
                .limit(1)
            )
            if experiment.status in DECIDED.values()
            else None
        )
        assert experiment.review_submitted_at is not None  # đã gửi duyệt
        assignee = experiment.review_assignee_id
        items.append(
            ReviewQueueItem(
                experiment=summaries[experiment.id],
                protocol=ProtocolRef(
                    id=ctx.protocol.id, name=ctx.protocol.name, status=ctx.protocol.status
                ),
                submitted_at=experiment.review_submitted_at,
                assignee=user_ref(session, assignee) if assignee is not None else None,
                claimed_at=experiment.claimed_at,
                decision=review,
                decided_at=experiment.decided_at if review is not None else None,
                max_relative_drop=_max_drop(session, experiment.id),
                required_cases_total=len(cases),
                required_cases_reviewed=sum(1 for c in cases if c.current_verdict is not None),
            )
        )
    if sort == "max_drop":
        items.sort(
            key=lambda i: (
                i.max_relative_drop is None,
                -(i.max_relative_drop or 0.0),
                i.submitted_at,
            )
        )
    else:
        items.sort(key=lambda i: (i.submitted_at, i.experiment.id))
    return items
