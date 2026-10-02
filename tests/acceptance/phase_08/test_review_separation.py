"""validation.md Phase 8, Nhận review và tách quyền (`test_review_separation.py`)."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from .conftest import (
    APPROVE,
    LEVELS,
    P5,
    Flow,
    detail,
    error,
    max_drop,
    ok,
    post,
    protocol_body,
    runs_of,
    unique,
)

pytestmark = pytest.mark.db


def _queue(client: Any, status: str) -> set[str]:
    response = client.get(f"/reviews?status={status}")
    assert response.status_code == 200, response.text
    return {item["experiment"]["id"] for item in response.json()}


def test_engineer_reviewer_cannot_review_own(api: Any) -> None:
    _, _, both = api.user("engineer", "reviewer")
    _, _, reviewer = api.user("reviewer")
    protocol = ok(
        post(reviewer, "/protocols", {"name": unique("p"), "body": protocol_body()})
    ).json()
    target = api.target()
    api.profile(target, sec=0.05, batch=5, attacks=["fgsm"])
    body = api.body(target, [P5.attack("fgsm", LEVELS)], protocol_id=protocol["id"])
    experiment_id = ok(post(both, "/experiments", body)).json()["id"]
    api.work(target, experiment_id)
    ok(post(both, f"/experiments/{experiment_id}/submit", {}))
    assert experiment_id not in _queue(both, "waiting")
    assert experiment_id in _queue(reviewer, "waiting")
    assert post(both, f"/reviews/{experiment_id}/claim").status_code == 403


def test_self_review_rejected_by_triggers(flow: Flow, app_engine: Engine) -> None:
    experiment_id = flow.submitted()
    with app_engine.begin() as conn, pytest.raises(DBAPIError, match="không được nhận review"):
        conn.execute(
            text("UPDATE experiments SET review_assignee_id = created_by WHERE id = :id"),
            {"id": experiment_id},
        )
    with app_engine.begin() as conn, pytest.raises(DBAPIError):
        conn.execute(
            text(
                "INSERT INTO reviews (experiment_id, reviewer_id, version, decision, conclusion)"
                " SELECT id, created_by, 1, 'approve', 'tự duyệt' FROM experiments WHERE id = :id"
            ),
            {"id": experiment_id},
        )


def test_second_reviewer_cannot_claim(flow: Flow) -> None:
    experiment_id = flow.in_review()
    _, _, second = flow.api.user("reviewer")
    assert error(flow.claim(experiment_id, second))[:2] == (409, "conflict")


def test_non_assignee_forbidden_before_field_checks(
    flow: Flow, fail_first_build: list[str]
) -> None:
    """403 đứng trước kiểm tra nghiệp vụ: một tiêu chí chưa kết luận (run lỗi), `approve` đúng
    schema nhưng thiếu `inconclusive_justification` → 403 với người không nhận review (người nhận:
    422).
    Body sai schema của contract (thiếu conclusion; approve thiếu mitigation, model_verdict; verdict
    `safety_relevant` thiếu mitigation) là 422 của framework, kiểm trước mọi thứ (người dùng chốt ở
    Group 7, 2026-10-02)."""
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
    failed = next(r for r in runs_of(flow.owner, experiment_id) if r["status"] == "failed")
    ok(flow.submit(experiment_id, run_explanations={failed["run_id"]: "Hết bộ nhớ"}))
    ok(flow.claim(experiment_id))
    _, _, second = flow.api.user("reviewer")
    case_id = flow.required_cases(experiment_id)[0]
    assert flow.verdict(experiment_id, case_id, second).status_code == 403
    assert flow.decide(experiment_id, second, **APPROVE).status_code == 403
    assert flow.decide(experiment_id, **APPROVE).status_code == 422  # người nhận: thiếu giải trình


@pytest.mark.parametrize("role", ["engineer", "admin"])
def test_non_reviewer_cannot_decide(flow: Flow, role: str) -> None:
    experiment_id = flow.in_review()
    client = flow.api.admin() if role == "admin" else flow.api.user(role)[2]
    assert flow.decide(experiment_id, client, **APPROVE).status_code == 403
    assert flow.claim(experiment_id, client).status_code == 403


def test_release_returns_to_queue(flow: Flow) -> None:
    experiment_id = flow.in_review()
    ok(post(flow.reviewer, f"/reviews/{experiment_id}/release"))
    after = detail(flow.owner, experiment_id)
    assert after.status == "submitted_for_review"
    assert after.review is not None and after.review.assignee is None
    _, _, second = flow.api.user("reviewer")
    assert experiment_id in _queue(second, "waiting")
    assert flow.claim(experiment_id, second).status_code == 200
    assert detail(second, experiment_id).status == "in_review"
