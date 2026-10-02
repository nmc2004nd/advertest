"""validation.md Phase 8, Gửi duyệt và khóa (`test_submit_lock.py`)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import Engine, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from backend.app.db import models as m

from .conftest import (
    DEV_OPEN,
    LEVELS,
    P5,
    Flow,
    error,
    ok,
    post,
    protocol_body,
    required_grid,
    runs_of,
    unique,
)

pytestmark = pytest.mark.db


def test_dev_open_cannot_be_submitted(flow: Flow) -> None:
    experiment_id = flow.experiment(protocol_id=DEV_OPEN)
    assert error(flow.submit(experiment_id))[:2] == (409, "conflict")


def test_unfinished_or_cancelled_cannot_be_submitted(flow: Flow) -> None:
    queued = flow.experiment(run=False)
    assert error(flow.submit(queued))[:2] == (409, "conflict")
    ok(post(flow.owner, f"/experiments/{queued}/cancel"))
    assert error(flow.submit(queued))[:2] == (409, "conflict")


def test_failed_required_run_needs_explanation(flow: Flow, fail_first_build: list[str]) -> None:
    experiment_id = flow.experiment()
    failed = [r for r in runs_of(flow.owner, experiment_id) if r["status"] == "failed"]
    assert len(failed) == 1 and fail_first_build, runs_of(flow.owner, experiment_id)
    status, _, paths = error(flow.submit(experiment_id))
    assert status == 422 and paths == [f"run_explanations.{failed[0]['run_id']}"]
    explained = flow.submit(
        experiment_id, run_explanations={failed[0]["run_id"]: "Hết bộ nhớ; chạy lại không đổi"}
    )
    assert explained.status_code == 200, explained.text


def test_stopped_limit_needs_explanation(flow: Flow, monkeypatch: pytest.MonkeyPatch) -> None:
    """Mỗi lần báo tiến độ tính như 100 giây, giới hạn 350 giây (như test Phase 6): lượt một (eps 2,
    8, 32) chạy xong, run kế tiếp chạm giới hạn → `stopped_limit`. Mọi level đều bắt buộc."""
    levels = [2.0, 4.0, 8.0, 16.0, 32.0]
    original = P5.WorkerClient.progress

    def slow(self: Any, run_id: UUID, body: Any) -> Any:
        return original(self, run_id, body.model_copy(update={"processing_seconds_delta": 100.0}))

    monkeypatch.setattr(P5.WorkerClient, "progress", slow)
    protocol = ok(
        post(
            flow.reviewer,
            "/protocols",
            {
                "name": unique("p"),
                "body": protocol_body(required_attacks=[required_grid("fgsm", levels)]),
            },
        )
    ).json()
    experiment_id = flow.experiment(
        attacks=[P5.attack("fgsm", levels)],
        protocol_id=protocol["id"],
        limit={"kind": "time", "value": "350"},
    )
    runs = runs_of(flow.owner, experiment_id)
    stopped = [r for r in runs if r["status"] == "stopped_limit"]
    assert stopped, [(r["level"], r["status"]) for r in runs]
    status, _, paths = error(flow.submit(experiment_id))
    assert status == 422
    assert {f"run_explanations.{r['run_id']}" for r in stopped} <= set(paths)
    reasons = {p.removeprefix("run_explanations."): "Chạm giới hạn thời gian" for p in paths}
    assert flow.submit(experiment_id, run_explanations=reasons).status_code == 200


def test_cached_run_needs_no_explanation(flow: Flow) -> None:
    flow.experiment()  # lần đầu chạy thật
    again = flow.experiment()  # cùng fingerprint: run `skipped` do `cached`
    runs = runs_of(flow.owner, again)
    assert {r["status"] for r in runs} == {"skipped"}, runs
    assert all(r["status_reason"]["code"] == "cached" for r in runs), runs
    assert flow.submit(again).status_code == 200


def test_early_stopped_run_needs_no_explanation(flow: Flow) -> None:
    """PGD L∞ làm model sụp ngay ở eps 2 (mức sụt khoảng 0.97, conftest Phase 7): level giữa bị
    `skipped` do `early_stop`."""
    levels = [2.0, 4.0, 8.0, 16.0, 32.0]
    flow.api.profile(flow.target, sec=0.05, batch=5, attacks=["pgd_linf"])
    body = protocol_body(
        required_attacks=[required_grid("pgd_linf", levels)],
        pass_criteria=[
            {
                "kind": "max_drop_at_level",
                "attack_spec_name": "pgd_linf",
                "level": 2.0,
                "threshold_kind": "relative_drop",
                "threshold": 1.0,
                "class_filter": None,
            }
        ],
    )
    protocol = ok(post(flow.reviewer, "/protocols", {"name": unique("p"), "body": body})).json()
    experiment_id = flow.experiment(
        attacks=[P5.attack("pgd_linf", levels)], protocol_id=protocol["id"]
    )
    skipped = [r for r in runs_of(flow.owner, experiment_id) if r["status"] == "skipped"]
    assert skipped and all(r["status_reason"]["code"] == "early_stop" for r in skipped), skipped
    assert flow.submit(experiment_id).status_code == 200


def test_dirty_runs_blocked_when_protocol_forbids(flow: Flow, dirty_tree: None) -> None:
    experiment_id = flow.experiment()
    status, code, _ = error(flow.submit(experiment_id))
    assert (status, code) == (409, "conflict")
    assert "chưa commit" in flow.submit(experiment_id).json()["error"]["message"]


def test_only_owner_submits(flow: Flow) -> None:
    experiment_id = flow.experiment()
    _, _, other = flow.api.user("engineer")
    assert post(other, f"/experiments/{experiment_id}/submit", {}).status_code == 403


def test_locked_after_submit(flow: Flow, app_engine: Engine) -> None:
    experiment_id = flow.submitted()
    assert error(post(flow.owner, f"/experiments/{experiment_id}/cancel"))[:2] == (
        409,
        "experiment_locked",
    )
    assert error(flow.submit(experiment_id))[:2] == (409, "experiment_locked")
    comment = {"target_type": "experiment", "target_id": experiment_id, "body": "Đã gửi, chờ duyệt"}
    assert post(flow.owner, f"/experiments/{experiment_id}/comments", comment).status_code == 201
    # Không có endpoint sửa experiment; ghi thẳng vào DB (sửa trường, thêm run) bị trigger chặn.
    with app_engine.begin() as conn, pytest.raises(DBAPIError, match="bị khóa"):
        conn.execute(
            text("UPDATE experiments SET name = 'sửa sau khi gửi' WHERE id = :id"),
            {"id": experiment_id},
        )
    with app_engine.begin() as conn, pytest.raises(DBAPIError, match="bị khóa"):
        conn.execute(
            text(
                "INSERT INTO runs SELECT (jsonb_populate_record(NULL::runs, to_jsonb(r)"
                " || jsonb_build_object('id', gen_random_uuid()))).*"
                " FROM runs r WHERE r.experiment_id = :id LIMIT 1"
            ),
            {"id": experiment_id},
        )


def test_submit_emails_every_active_reviewer_except_owner(api: Any, app_engine: Engine) -> None:
    """Người tạo có cả role reviewer: không nhận email của chính mình."""
    owner_id, owner_email, owner = api.user("engineer", "reviewer")
    _, other_email, other = api.user("reviewer")
    disabled_id, disabled_email, _ = api.user("reviewer")
    ok(post(api.admin(), f"/admin/users/{disabled_id}/disable", {}))
    protocol = ok(post(other, "/protocols", {"name": unique("p"), "body": protocol_body()})).json()
    target = api.target()
    api.profile(target, sec=0.05, batch=5, attacks=["fgsm"])
    body = api.body(target, [P5.attack("fgsm", LEVELS)], protocol_id=protocol["id"])
    experiment_id = ok(post(owner, "/experiments", body)).json()["id"]
    api.work(target, experiment_id)
    ok(post(owner, f"/experiments/{experiment_id}/submit", {}))
    with Session(app_engine) as session:
        active = set(
            session.scalars(
                select(m.User.email)
                .join(m.UserRole, m.UserRole.user_id == m.User.id)
                .where(m.User.status == "active", m.UserRole.role == "reviewer")
            )
        )
        sent = [
            e
            for e in session.scalars(select(m.EmailOutbox))
            if f"/reviews/{experiment_id}" in e.body_text
        ]
    recipients = {e.to for e in sent}
    assert len(sent) == len(recipients)  # mỗi người một email
    assert recipients == active - {owner_email}
    assert other_email in recipients
    assert owner_email not in recipients and disabled_email not in recipients
    assert owner_id


def test_hidden_unanonymized_required_case_blocks_submit(flow: Flow, owner_engine: Engine) -> None:
    """Case bắt buộc chưa làm mờ (dữ liệu trước Phase 6) → 409."""
    experiment_id = flow.experiment()
    run_ids = [UUID(r["run_id"]) for r in runs_of(flow.owner, experiment_id)]
    with Session(owner_engine) as session, session.begin():
        session.execute(
            update(m.FailureCase)
            .where(m.FailureCase.run_id.in_(run_ids))
            .values(anonymization=None)
        )
    status, code, _ = error(flow.submit(experiment_id))
    assert (status, code) == (409, "conflict")
