"""validation.md Phase 8, Verdict (`test_verdicts.py`)."""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import Engine, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from backend.app.db import models as m

from .conftest import CASES_PER_ATTACK, Flow, detail, error, ok, post, runs_of

pytestmark = pytest.mark.db


def test_two_verdicts_two_versions(flow: Flow) -> None:
    experiment_id = flow.in_review()
    case_id = flow.required_cases(experiment_id)[0]
    first = ok(flow.verdict(experiment_id, case_id, severity="minor")).json()
    second = ok(
        flow.verdict(
            experiment_id,
            case_id,
            severity="critical",
            kind="safety_relevant",
            mitigation="Thêm dữ liệu đêm",
        )
    ).json()
    assert (first["version"], second["version"]) == (1, 2)
    history = flow.reviewer.get(f"/failure-cases/{case_id}/verdicts").json()
    assert [v["version"] for v in history] == [2, 1]
    assert history[1]["severity"] == "minor"  # bản cũ vẫn đọc được, không đổi
    review = detail(flow.reviewer, experiment_id).review
    assert review is not None
    current = {str(c.failure_case_id): c.current_verdict for c in review.required_cases}
    assert current[case_id] is not None and current[case_id].version == 2


def test_safety_relevant_needs_mitigation(flow: Flow) -> None:
    experiment_id = flow.in_review()
    case_id = flow.required_cases(experiment_id)[0]
    response = flow.verdict(experiment_id, case_id, kind="safety_relevant", mitigation=None)
    assert response.status_code == 422, response.text


def test_frozen_after_decision(flow: Flow, app_engine: Engine) -> None:
    experiment_id = flow.approved()
    case_id = flow.required_cases(experiment_id)[0]
    run_id = runs_of(flow.owner, experiment_id)[0]["run_id"]
    assert error(flow.verdict(experiment_id, case_id))[0] == 409
    comment = {"target_type": "experiment", "target_id": experiment_id, "body": "còn câu hỏi"}
    assert post(flow.owner, f"/experiments/{experiment_id}/comments", comment).status_code == 409
    resubmit = flow.submit(experiment_id, run_explanations={run_id: "giải trình muộn"})
    assert resubmit.status_code == 409
    # Ghi thẳng vào DB cũng bị trigger chặn.
    with Session(app_engine) as session:
        reviewer = session.scalars(
            select(m.CaseVerdict.reviewer_id).where(m.CaseVerdict.failure_case_id == UUID(case_id))
        ).first()
    statements = [
        (
            "INSERT INTO case_verdicts (failure_case_id, version, severity, kind, reviewer_id)"
            " VALUES (:case, 99, 'minor', 'acceptable', :reviewer)"
        ),
        (
            "INSERT INTO review_comments (experiment_id, author_id, target_type, target_id, body)"
            " VALUES (:exp, :reviewer, 'experiment', :exp, 'muộn')"
        ),
        ("INSERT INTO run_explanations (run_id, author_id, text) VALUES (:run, :reviewer, 'muộn')"),
    ]
    for statement in statements:
        with app_engine.begin() as conn, pytest.raises(DBAPIError):
            conn.execute(
                text(statement),
                {"case": case_id, "reviewer": reviewer, "exp": experiment_id, "run": run_id},
            )


def test_comment_rules(flow: Flow) -> None:
    completed = flow.experiment()
    comment = {"target_type": "experiment", "target_id": completed, "body": "hỏi trước khi gửi"}
    assert error(post(flow.owner, f"/experiments/{completed}/comments", comment))[0] == 409
    submitted = flow.submitted()
    foreign = {
        "target_type": "run",
        "target_id": runs_of(flow.owner, completed)[0]["run_id"],
        "body": "x",
    }
    assert post(flow.owner, f"/experiments/{submitted}/comments", foreign).status_code == 422
    mine = {"target_type": "experiment", "target_id": submitted, "body": "ok"}
    assert post(flow.api.admin(), f"/experiments/{submitted}/comments", mine).status_code == 403
    assert post(flow.reviewer, f"/experiments/{submitted}/comments", mine).status_code == 201


def test_append_only_tables(flow: Flow, app_engine: Engine, fail_first_build: list[str]) -> None:
    """Có đủ dòng ở cả ba bảng (run lỗi kèm giải trình, verdict, bình luận); `UPDATE`/`DELETE`
    bằng `advertest_app` đều bị từ chối."""
    experiment_id = flow.experiment()
    failed = next(r for r in runs_of(flow.owner, experiment_id) if r["status"] == "failed")
    ok(flow.submit(experiment_id, run_explanations={failed["run_id"]: "Hết bộ nhớ"}))
    ok(flow.claim(experiment_id))
    case_id = flow.required_cases(experiment_id)[0]
    ok(flow.verdict(experiment_id, case_id))
    ok(
        post(
            flow.owner,
            f"/experiments/{experiment_id}/comments",
            {"target_type": "experiment", "target_id": experiment_id, "body": "ghi chú"},
        )
    )
    for table, where in [
        ("case_verdicts", "failure_case_id = :case"),
        ("review_comments", "experiment_id = :exp"),
        ("run_explanations", "run_id = :run"),
    ]:
        params = {"case": case_id, "exp": experiment_id, "run": failed["run_id"]}
        with app_engine.connect() as conn:
            assert conn.execute(
                text(f"SELECT count(*) FROM {table} WHERE {where}"), params
            ).scalar()
        for statement in (
            f"UPDATE {table} SET created_at = created_at WHERE {where}",
            f"DELETE FROM {table} WHERE {where}",
        ):
            with app_engine.begin() as conn, pytest.raises(DBAPIError):
                conn.execute(text(statement), params)


def test_required_cases_top_n_per_attack(flow: Flow, app_engine: Engine) -> None:
    experiment_id = flow.submitted()
    run_ids = [UUID(r["run_id"]) for r in runs_of(flow.owner, experiment_id)]
    with Session(app_engine) as session:
        cases = session.scalars(
            select(m.FailureCase).where(m.FailureCase.run_id.in_(run_ids))
        ).all()
    expected = [
        str(c.id)
        for c in sorted(cases, key=lambda c: (-c.severity_score, c.image_id))[:CASES_PER_ATTACK]
    ]
    assert flow.required_cases(experiment_id) == expected
    assert flow.required_cases(experiment_id) == expected  # đọc lại: cùng thứ tự
