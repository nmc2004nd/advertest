"""Email của vòng review qua outbox (requirements.md Phase 8, Gửi duyệt và Quyết định): chỉ có tên
experiment, protocol, câu tóm tắt và link; không có ảnh hay dữ liệu dataset."""

from __future__ import annotations

import html

from sqlalchemy import select
from sqlalchemy.orm import Session

from advertest_contracts.enums import ModelVerdict, ReviewDecision, Role, UserStatus
from backend.app.db import models as m
from backend.app.services.notifications import app_base_url

DECISION_TEXT = {
    ReviewDecision.APPROVE: "đã được chấp nhận",
    ReviewDecision.CHANGES_REQUESTED: "được yêu cầu sửa",
    ReviewDecision.REJECT: "bị từ chối",
}
VERDICT_TEXT = {
    ModelVerdict.MEETS_CRITERIA: "model đạt tiêu chí",
    ModelVerdict.DOES_NOT_MEET: "model không đạt tiêu chí",
    ModelVerdict.CONDITIONAL: "model đạt có điều kiện",
}
FOOTER = "Email tự động từ AdverTest."


def _enqueue(session: Session, to: str, subject: str, lines: list[str], link: str) -> None:
    text = "\n\n".join([*lines, f"Xem chi tiết: {link}", FOOTER]) + "\n"
    body_html = (
        '<!doctype html><html lang="vi"><body style="font-family: sans-serif">'
        + "".join(f"<p>{html.escape(line)}</p>" for line in lines)
        + f'<p><a href="{html.escape(link, quote=True)}">Mở trong AdverTest</a></p>'
        + f'<p style="color: #666; font-size: 12px">{FOOTER}</p></body></html>'
    )
    session.add(m.EmailOutbox(to=to, subject=subject, body_html=body_html, body_text=text))


def active_reviewers(session: Session, exclude: object) -> list[m.User]:
    return list(
        session.scalars(
            select(m.User)
            .join(m.UserRole, m.UserRole.user_id == m.User.id)
            .where(
                m.UserRole.role == Role.REVIEWER,
                m.User.status == UserStatus.ACTIVE,
                m.User.id != exclude,
            )
            .order_by(m.User.email)
        )
    )


def submitted(session: Session, experiment: m.Experiment, protocol: m.Protocol) -> int:
    """Email cho mọi reviewer `active` trừ người tạo; trả số email."""
    owner = session.get(m.User, experiment.created_by)
    assert owner is not None  # khóa ngoại
    reviewers = active_reviewers(session, experiment.created_by)
    link = f"{app_base_url()}/reviews/{experiment.id}"
    for reviewer in reviewers:
        _enqueue(
            session,
            reviewer.email,
            f'[AdverTest] Experiment "{experiment.name}" chờ duyệt',
            [
                f'{owner.full_name} đã gửi duyệt experiment "{experiment.name}"'
                f" theo protocol {protocol.name} v{protocol.version}.",
                "Experiment đang chờ một reviewer nhận.",
            ],
            link,
        )
    return len(reviewers)


def decided(session: Session, experiment: m.Experiment, review: m.Review) -> None:
    owner = session.get(m.User, experiment.created_by)
    assert owner is not None  # khóa ngoại
    lines = [f'Experiment "{experiment.name}" {DECISION_TEXT[review.decision]}.']
    if review.model_verdict is not None:
        lines.append(f"Kết luận về model: {VERDICT_TEXT[review.model_verdict]}.")
    _enqueue(
        session,
        owner.email,
        f'[AdverTest] Experiment "{experiment.name}" {DECISION_TEXT[review.decision]}',
        lines,
        f"{app_base_url()}/experiments/{experiment.id}",
    )
