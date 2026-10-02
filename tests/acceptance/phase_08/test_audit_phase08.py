"""validation.md Phase 8, Audit (`test_audit_phase08.py`).

Một luồng đầy đủ thực hiện mọi action của requirements.md mục Audit log; mỗi lần thực hiện tạo
đúng một dòng với actor và entity đúng. `report.generation_failed` kiểm cùng luồng ép lỗi trong
`test_report.py::test_failure_then_regenerate_keeps_id`.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from backend.app.db import models as m

from .conftest import APPROVE, Flow, ok, post, protocol_body, runs_of, unique

pytestmark = pytest.mark.db
ACTIONS = {
    "protocol.created",
    "protocol.versioned",
    "protocol.retired",
    "experiment.submitted",
    "review.claimed",
    "review.released",
    "case_verdict.recorded",
    "review.comment_added",
    "run_explanation.added",
    "review.decided",
    "report.generated",
    "report.downloaded",
}


def test_every_phase08_action_audited_once(
    flow: Flow, app_engine: Engine, fail_first_build: list[str]
) -> None:
    reviewer, owner = flow.reviewer_id, flow.owner_id
    v1 = ok(
        post(flow.reviewer, "/protocols", {"name": unique("p"), "body": protocol_body()})
    ).json()
    v2 = ok(
        post(flow.reviewer, f"/protocols/{v1['id']}/versions", {"body": protocol_body()})
    ).json()

    experiment_id = flow.experiment(protocol_id=v2["id"])
    failed = next(r for r in runs_of(flow.owner, experiment_id) if r["status"] == "failed")
    ok(flow.submit(experiment_id, run_explanations={failed["run_id"]: "Hết bộ nhớ"}))
    ok(flow.claim(experiment_id))
    ok(post(flow.reviewer, f"/reviews/{experiment_id}/release"))
    second_id, _, second = flow.api.user("reviewer")
    ok(flow.claim(experiment_id, second))
    cases = flow.required_cases(experiment_id)
    for case_id in cases:
        assert flow.verdict(experiment_id, case_id, second).status_code == 201
    ok(
        post(
            flow.owner,
            f"/experiments/{experiment_id}/comments",
            {"target_type": "experiment", "target_id": experiment_id, "body": "Đã giải trình"},
        )
    )
    ok(flow.decide(experiment_id, second, **{**APPROVE, "inconclusive_justification": "Run lỗi"}))
    report = flow.owner.get(f"/experiments/{experiment_id}").json()["report"]
    ok(second.get(f"/reports/{report['id']}/download?format=pdf"))
    ok(post(flow.reviewer, f"/protocols/{v2['id']}/retire"))

    exp, rep = UUID(experiment_id), UUID(report["id"])
    expected = {
        ("protocol.created", UUID(v1["id"]), reviewer),
        ("protocol.versioned", UUID(v2["id"]), reviewer),
        ("protocol.retired", UUID(v1["id"]), reviewer),  # version mới tự ngừng dùng bản cũ
        ("protocol.retired", UUID(v2["id"]), reviewer),
        ("experiment.submitted", exp, owner),
        ("run_explanation.added", UUID(failed["run_id"]), owner),
        ("review.claimed", exp, reviewer),
        ("review.released", exp, reviewer),
        ("review.claimed", exp, second_id),
        *{("case_verdict.recorded", UUID(c), second_id) for c in cases},
        ("review.comment_added", exp, owner),
        ("review.decided", exp, second_id),
        ("report.generated", rep, None),  # hệ thống
        ("report.downloaded", rep, second_id),
    }
    entities = {
        UUID(v1["id"]),
        UUID(v2["id"]),
        exp,
        rep,
        UUID(failed["run_id"]),
        *(UUID(c) for c in cases),
    }
    with Session(app_engine) as session:
        rows = session.scalars(
            select(m.AuditLog).where(
                m.AuditLog.action.in_(ACTIONS), m.AuditLog.entity_id.in_(entities)
            )
        ).all()
    actual = [(r.action, r.entity_id, r.actor_id) for r in rows]
    assert sorted(actual, key=str) == sorted(expected, key=str)
    assert {a for a, _, _ in actual} == ACTIONS
