"""validation.md Phase 8, Quyết định (`test_decision.py`)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import Engine, select, text, update
from sqlalchemy.orm import Session

from backend.app.db import models as m

from .conftest import (
    APPROVE,
    DEV_OPEN,
    Flow,
    audit_count,
    detail,
    error,
    max_drop,
    ok,
    post,
    protocol_body,
    unique,
)

pytestmark = pytest.mark.db


def test_approve_without_verdicts_is_409_with_checklist(flow: Flow) -> None:
    experiment_id = flow.in_review()
    first = flow.required_cases(experiment_id)[0]
    ok(flow.verdict(experiment_id, first))
    response = flow.decide(experiment_id, **APPROVE)
    assert error(response)[:2] == (409, "checklist_incomplete")
    checklist = {i["code"]: i for i in response.json()["error"]["checklist"]}
    # Chỉ gồm điều kiện trạng thái phía server.
    assert set(checklist) == {"protocol_not_dev", "required_cases_reviewed"}
    assert checklist["protocol_not_dev"]["satisfied"] is True
    assert checklist["required_cases_reviewed"]["satisfied"] is False


def test_dev_protocol_fails_checklist(flow: Flow, owner_engine: Engine) -> None:
    """Experiment dev-open không gửi duyệt được; dữ liệu cũ đã ở `in_review` mà gắn protocol dev
    (ghi thẳng DB để giả lập) bị checklist chặn."""
    experiment_id = flow.in_review()
    flow.review_all(experiment_id)
    # Experiment đã khóa (trigger chặn mọi sửa đổi): chủ bảng tắt trigger trong giao dịch dựng dữ
    # liệu cũ rồi bật lại.
    with owner_engine.begin() as conn:
        conn.execute(text("ALTER TABLE experiments DISABLE TRIGGER USER"))
        conn.execute(
            update(m.Experiment)
            .where(m.Experiment.id == UUID(experiment_id))
            .values(protocol_id=UUID(DEV_OPEN))
        )
        conn.execute(text("ALTER TABLE experiments ENABLE TRIGGER USER"))
    response = flow.decide(experiment_id, **APPROVE)
    assert error(response)[:2] == (409, "checklist_incomplete")
    checklist = {i["code"]: i["satisfied"] for i in response.json()["error"]["checklist"]}
    assert checklist["protocol_not_dev"] is False


@pytest.mark.parametrize("missing", ["conclusion", "mitigation", "model_verdict"])
def test_approve_missing_field_is_422(flow: Flow, missing: str) -> None:
    experiment_id = flow.in_review()
    flow.review_all(experiment_id)
    body = {k: v for k, v in APPROVE.items() if k != missing}
    assert flow.decide(experiment_id, **body).status_code == 422


def test_inconclusive_needs_justification(flow: Flow, fail_first_build: list[str]) -> None:
    protocol = ok(
        post(
            flow.reviewer,
            "/protocols",
            {
                "name": unique("p"),
                "body": protocol_body(pass_criteria=[max_drop("fgsm", 2.0), max_drop("fgsm", 4.0)]),
            },
        )
    ).json()
    experiment_id = flow.experiment(protocol_id=protocol["id"])
    failed = next(
        r
        for r in flow.owner.get(f"/experiments/{experiment_id}/runs").json()
        if r["status"] == "failed"
    )
    ok(flow.submit(experiment_id, run_explanations={failed["run_id"]: "Hết bộ nhớ"}))
    ok(flow.claim(experiment_id))
    flow.review_all(experiment_id)
    assert flow.decide(experiment_id, **APPROVE).status_code == 422
    justified = {**APPROVE, "inconclusive_justification": "Level còn lại đạt; run lỗi do máy"}
    assert flow.decide(experiment_id, **justified).status_code == 200


def test_approve_records_review_audit_and_email(flow: Flow, app_engine: Engine) -> None:
    experiment_id = flow.in_review()
    flow.review_all(experiment_id)
    before = detail(flow.reviewer, experiment_id).review
    assert before is not None
    with Session(app_engine) as session:
        query = select(m.EmailOutbox.id).where(m.EmailOutbox.to == flow.owner_email)
        earlier = set(session.scalars(query))
    ok(flow.decide(experiment_id, **APPROVE))
    after = detail(flow.owner, experiment_id)
    assert after.status == "approved"
    with Session(app_engine) as session:
        (review,) = session.scalars(
            select(m.Review).where(m.Review.experiment_id == UUID(experiment_id))
        ).all()
        emails = [
            e
            for e in session.scalars(
                select(m.EmailOutbox).where(m.EmailOutbox.to == flow.owner_email)
            )
            if f"/experiments/{experiment_id}" in e.body_text and e.id not in earlier
        ]
    assert review.decision == "approve" and review.reviewer_id == flow.reviewer_id
    assert review.criteria_results == [r.model_dump(mode="json") for r in before.criteria_results]
    assert [c["satisfied"] for c in review.checklist] == [True, True]
    assert audit_count(app_engine, "review.decided", experiment_id) == 1
    assert len(emails) == 1


@pytest.mark.parametrize(
    ("decision", "status"), [("changes_requested", "changes_requested"), ("reject", "rejected")]
)
def test_changes_requested_and_reject_need_only_conclusion(
    flow: Flow, decision: str, status: str
) -> None:
    experiment_id = flow.in_review()  # chưa ghi verdict nào
    assert flow.decide(experiment_id, decision=decision).status_code == 422
    response = flow.decide(experiment_id, decision=decision, conclusion="Thiếu fog trong lần chạy")
    assert response.status_code == 200, response.text
    assert detail(flow.owner, experiment_id).status == status
    # Trạng thái cuối: không quyết định lại được.
    assert flow.decide(experiment_id, **APPROVE).status_code == 409


def test_approve_with_model_does_not_meet(flow: Flow) -> None:
    experiment_id = flow.in_review()
    flow.review_all(experiment_id)
    response = flow.decide(experiment_id, **{**APPROVE, "model_verdict": "does_not_meet"})
    assert response.status_code == 200, response.text
    after = detail(flow.owner, experiment_id)
    assert after.status == "approved"
    assert after.review is not None and after.review.model_verdict == "does_not_meet"


def test_clone_after_changes_requested(flow: Flow) -> None:
    experiment_id = flow.in_review()
    ok(flow.decide(experiment_id, decision="changes_requested", conclusion="Thêm level eps 8"))
    clone: dict[str, Any] = ok(flow.owner.get(f"/experiments/{experiment_id}/clone")).json()
    created = ok(post(flow.owner, "/experiments", clone["config"])).json()
    assert created["cloned_from"] == experiment_id
