"""`ReportView` đọc từ DB (dùng cả trong `ExperimentDetail.report`); không import phần sinh
report để `experiment_views` import được mà không vòng lặp."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from advertest_contracts.models import ReportView
from backend.app.db import models as m
from backend.app.reviews.views import user_ref


def view(session: Session, report: m.Report) -> ReportView:
    experiment = session.get(m.Experiment, report.experiment_id)
    review = session.scalar(
        select(m.Review)
        .where(m.Review.experiment_id == report.experiment_id)
        .order_by(m.Review.version.desc())
        .limit(1)
    )
    assert experiment is not None and experiment.decided_at is not None
    assert review is not None and review.model_verdict is not None
    return ReportView(
        id=report.id,
        experiment_id=report.experiment_id,
        experiment_name=experiment.name,
        status=report.status,
        model_verdict=review.model_verdict,
        approved_by=user_ref(session, report.approved_by),
        approved_at=experiment.decided_at,
        generated_at=report.generated_at,
        json_sha256=report.json_sha256,
        pdf_sha256=report.pdf_sha256,
    )


def for_experiment(session: Session, experiment_id: UUID) -> ReportView | None:
    report = session.scalar(select(m.Report).where(m.Report.experiment_id == experiment_id))
    return view(session, report) if report is not None else None
