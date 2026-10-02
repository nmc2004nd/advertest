"""Phase 8 Group 2: gửi duyệt, khóa, nhận review, verdict, tiêu chí, quyết định, bình luận, audit
(plan task 11-18; validation.md các mục test_submit_lock, test_review_separation, test_verdicts,
test_criteria, test_decision, test_audit_phase08)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from advertest_contracts.enums import (
    ChecklistCode,
    CriterionStatus,
    ExperimentStatus,
    LimitKind,
    ProtocolStatus,
    ReviewDecision,
    Role,
    RunStatus,
)
from advertest_contracts.hashing import sha256_of
from advertest_contracts.models import (
    AttackConfig,
    CaseVerdictView,
    ErrorResponse,
    ExperimentConfig,
    ExperimentDetail,
    Limit,
    ProtocolBody,
    ReviewComment,
    ReviewQueueItem,
)
from attacks.registry import get_spec, load_catalog
from backend.app.db import models as m

from .test_experiment_api import DEV_OPEN, Api, Fx, _post, api, env, fx, world
from .test_worker_services import T0, _attack

pytestmark = pytest.mark.db
__all__ = ["api", "env", "fx", "world"]


def _sha() -> str:
    return uuid.uuid4().hex * 2


def _metrics(drop: float, *, partial: bool = False) -> dict[str, Any]:
    clean = 0.5
    return {
        "clean": {"map50": clean, "map50_95": 0.3},
        "attacked": {"map50": clean * (1 - drop), "map50_95": 0.2},
        "relative_drop": drop,
        "absolute_drop": clean * drop,
        "attack_success_rate": 0.4,
        "per_class": None,
        "partial": partial,
    }


def _protocol(owner_engine: Engine, **extra: Any) -> uuid.UUID:
    """kitti-baseline thu nhỏ: FGSM eps 2, 4 và PGD L∞ eps 2; 2 case bắt buộc mỗi attack."""
    catalog = load_catalog()
    body = ProtocolBody.model_validate(
        {
            "description": "Review Group 2",
            "required_attacks": [
                {
                    "attack_spec_name": "fgsm",
                    "spec_sha256": get_spec(catalog, name="fgsm").spec_sha256,
                    "mode": "grid",
                    "grid": {"levels": [2, 4]},
                },
                {
                    "attack_spec_name": "pgd_linf",
                    "spec_sha256": get_spec(catalog, name="pgd_linf").spec_sha256,
                    "mode": "grid",
                    "grid": {"levels": [2]},
                },
            ],
            "min_slice_size": 1,
            "pass_criteria": [
                {
                    "kind": "max_drop_at_level",
                    "attack_spec_name": "fgsm",
                    "level": 4,
                    "threshold_kind": "relative_drop",
                    "threshold": 0.5,
                },
                {
                    "kind": "max_drop_at_level",
                    "attack_spec_name": "pgd_linf",
                    "level": 2,
                    "threshold_kind": "relative_drop",
                    "threshold": 0.3,
                },
            ],
            "cases_to_review_per_attack": 2,
            **extra,
        }
    )
    with Session(owner_engine) as s, s.begin():
        creator = s.scalar(select(m.User.id).limit(1))
        row = m.Protocol(
            name=f"g2-{uuid.uuid4().hex[:8]}", version=1, body=body.model_dump(mode="json"),
            body_sha256=sha256_of(body), status=ProtocolStatus.ACTIVE, created_by=creator,
        )  # fmt: skip
        s.add(row)
        s.flush()
        return row.id


@dataclass
class Exp:
    id: uuid.UUID
    runs: dict[str, uuid.UUID] = field(default_factory=dict)
    cases: dict[str, list[uuid.UUID]] = field(default_factory=dict)


# (attack, level) → (trạng thái, mức sụt, mã lý do)
RUNS: dict[tuple[str, float], tuple[RunStatus, float | None, str | None]] = {
    ("fgsm", 2): (RunStatus.COMPLETED, 0.2, None),
    ("fgsm", 4): (RunStatus.COMPLETED, 0.4, None),
    ("pgd_linf", 2): (RunStatus.COMPLETED, 0.9, None),
}


def _experiment(
    owner_engine: Engine,
    fx: Fx,
    owner: uuid.UUID,
    protocol: uuid.UUID | str,
    *,
    runs: dict[tuple[str, float], tuple[RunStatus, float | None, str | None]] | None = None,
    status: ExperimentStatus = ExperimentStatus.COMPLETED,
    dirty: bool = False,
    anonymized: bool = True,
) -> Exp:
    """Experiment đã chạy xong (dựng thẳng trong DB), mỗi run 3 failure case điểm 3, 2, 1."""
    plan = runs or RUNS
    levels: dict[str, list[float]] = {}
    for name, level in plan:
        levels.setdefault(name, []).append(level)
    config = ExperimentConfig(
        protocol_id=uuid.UUID(str(protocol)),
        model_version_id=fx.model,
        slice_id=fx.slice,
        class_mapping_id=fx.mapping,
        compute_target_id=fx.target,
        attacks=[AttackConfig.model_validate(_attack(name, lv)) for name, lv in levels.items()],
        limit=Limit(kind=LimitKind.TIME, value=Decimal(7200)),
    )
    out: Exp
    with Session(owner_engine) as s, s.begin():
        exp = m.Experiment(
            name=f"g2-{uuid.uuid4().hex[:6]}", created_by=owner, protocol_id=config.protocol_id,
            model_version_id=fx.model, slice_id=fx.slice, class_mapping_id=fx.mapping,
            compute_target_id=fx.target, config=config.model_dump(mode="json"),
            config_sha256=sha256_of(config), status=status, limit_kind=LimitKind.TIME,
            limit_value=7200, created_at=T0, submitted_at=T0,
            finished_at=None if status == ExperimentStatus.RUNNING else T0 + timedelta(hours=1),
        )  # fmt: skip
        s.add(exp)
        s.flush()
        out = Exp(exp.id)
        catalog = load_catalog()
        for ordinal, ((name, level), (run_status, drop, code)) in enumerate(plan.items()):
            spec = get_spec(catalog, name=name)
            reason: dict[str, str] | None = None
            if code == "early_stop":  # run kích hoạt: run đầu tiên của experiment
                trigger = str(out.runs[next(iter(out.runs))])
                reason = {"code": code, "message": "x", "trigger_run_id": trigger}
            elif code is not None:
                reason = {"code": code, "message": "x"}
            done = run_status == RunStatus.COMPLETED
            run = m.Run(
                experiment_id=exp.id, attack_spec_id=spec.id, level=level, params={}, seed=0,
                fingerprint=_sha(), status=run_status, status_reason=reason, images_total=2,
                images_done=2 if done else 0,
                metrics=_metrics(drop) if drop is not None else None,
                manifest_uri=f"s3://artifacts/runs/{uuid.uuid4()}/manifest.json" if done else None,
                ordinal=ordinal, git_dirty=dirty, finished_at=T0,
            )  # fmt: skip
            s.add(run)
            s.flush()
            key = f"{name}_{level:g}"
            out.runs[key] = run.id
            out.cases[key] = []
            for rank, score in enumerate((3.0, 2.0, 1.0)):
                case = m.FailureCase(
                    run_id=run.id, image_id=f"{rank:06d}", severity_score=score,
                    fingerprint=_sha(), rank=rank, lost_objects=int(score),
                    new_false_positives=0, detections={}, artifacts={},
                    anonymization=(
                        {"applied": True, "method": "rule_v1", "version": 1, "regions_count": 1}
                        if anonymized
                        else None
                    ),
                )  # fmt: skip
                s.add(case)
                s.flush()
                out.cases[key].append(case.id)
    return out


def _err(response: httpx.Response) -> tuple[int, str]:
    error = ErrorResponse.model_validate(response.json()).error
    return response.status_code, error.code


def _detail(client: TestClient, experiment: uuid.UUID) -> ExperimentDetail:
    response = client.get(f"/experiments/{experiment}")
    assert response.status_code == 200, response.text
    return ExperimentDetail.model_validate(response.json())


def _submit(client: TestClient, exp: Exp, **explanations: str) -> httpx.Response:
    body = {
        "note": "gửi",
        "run_explanations": {str(exp.runs[k]): v for k, v in explanations.items()},
    }
    return _post(client, f"/experiments/{exp.id}/submit", body)


def _verdict(client: TestClient, exp: Exp, case: uuid.UUID, **body: Any) -> httpx.Response:
    payload = {"severity": "major", "kind": "acceptable", **body}
    return _post(client, f"/reviews/{exp.id}/cases/{case}/verdicts", payload)


APPROVE = {
    "decision": "approve",
    "model_verdict": "does_not_meet",
    "conclusion": "Bài test đúng protocol; model không đạt",
    "mitigation": "Adversarial training",
}


@dataclass
class Flow:
    owner: TestClient
    owner_id: uuid.UUID
    reviewer: TestClient
    reviewer_id: uuid.UUID
    exp: Exp


def _flow(api: Api, fx: Fx, owner_engine: Engine, **kw: Any) -> Flow:
    owner_id, owner = api.client(Role.ENGINEER)
    reviewer_id, reviewer = api.client(Role.REVIEWER)
    exp = _experiment(owner_engine, fx, owner_id, kw.pop("protocol", None) or
                      _protocol(owner_engine), **kw)  # fmt: skip
    return Flow(owner, owner_id, reviewer, reviewer_id, exp)


def _review_all(flow: Flow) -> None:
    detail = _detail(flow.reviewer, flow.exp.id)
    assert detail.review is not None
    for case in detail.review.required_cases:
        assert _verdict(flow.reviewer, flow.exp, case.failure_case_id).status_code == 201


def _audit(engine: Engine, entity: uuid.UUID, action: str) -> int:
    with Session(engine) as s:
        return (
            s.scalar(
                select(func.count())
                .select_from(m.AuditLog)
                .where(m.AuditLog.entity_id == entity, m.AuditLog.action == action)
            )
            or 0
        )


# ---------------------------------------------------------------- gửi duyệt và khóa


def test_dev_open_cannot_be_submitted(api: Api, fx: Fx, owner_engine: Engine) -> None:
    flow = _flow(api, fx, owner_engine, protocol=DEV_OPEN)
    detail = _detail(flow.owner, flow.exp.id)
    assert detail.submit_check is not None and not detail.submit_check[1].satisfied
    assert _err(_submit(flow.owner, flow.exp)) == (409, "conflict")


@pytest.mark.parametrize("status", [ExperimentStatus.RUNNING, ExperimentStatus.CANCELLED])
def test_unfinished_cannot_be_submitted(
    api: Api, fx: Fx, owner_engine: Engine, status: ExperimentStatus
) -> None:
    flow = _flow(api, fx, owner_engine, status=status)
    assert _err(_submit(flow.owner, flow.exp)) == (409, "conflict")


def test_failed_required_run_needs_explanation(api: Api, fx: Fx, owner_engine: Engine) -> None:
    runs = {**RUNS, ("pgd_linf", 2): (RunStatus.FAILED, None, "error")}
    flow = _flow(api, fx, owner_engine, runs=runs)
    detail = _detail(flow.owner, flow.exp.id)
    assert detail.runs_requiring_explanation == [flow.exp.runs["pgd_linf_2"]]
    response = _submit(flow.owner, flow.exp)
    assert _err(response) == (422, "invalid_request")
    paths = [f.path for f in ErrorResponse.model_validate(response.json()).error.fields or []]
    assert paths == [f"run_explanations.{flow.exp.runs['pgd_linf_2']}"]
    extra = _submit(flow.owner, flow.exp, pgd_linf_2="hết bộ nhớ", fgsm_2="không cần")
    assert _err(extra) == (422, "invalid_request")
    ok = _submit(flow.owner, flow.exp, pgd_linf_2="hết bộ nhớ")
    assert ok.status_code == 200, ok.text
    review = ExperimentDetail.model_validate(ok.json()).review
    assert review is not None and [e.text for e in review.run_explanations] == ["hết bộ nhớ"]


@pytest.mark.parametrize("code", ["cached", "early_stop"])
def test_skipped_cached_or_early_stop_needs_no_explanation(
    api: Api, fx: Fx, owner_engine: Engine, code: str
) -> None:
    drop = 0.9 if code == "cached" else None
    runs = {**RUNS, ("fgsm", 4): (RunStatus.SKIPPED, drop, code)}
    flow = _flow(api, fx, owner_engine, runs=runs)
    assert _submit(flow.owner, flow.exp).status_code == 200


def test_stopped_limit_needs_explanation(api: Api, fx: Fx, owner_engine: Engine) -> None:
    runs = {**RUNS, ("fgsm", 4): (RunStatus.STOPPED_LIMIT, None, "time")}
    flow = _flow(api, fx, owner_engine, runs=runs)
    assert _err(_submit(flow.owner, flow.exp)) == (422, "invalid_request")


def test_dirty_runs(api: Api, fx: Fx, owner_engine: Engine) -> None:
    flow = _flow(api, fx, owner_engine, dirty=True)
    assert _err(_submit(flow.owner, flow.exp)) == (409, "conflict")
    allowed = _flow(
        api, fx, owner_engine, dirty=True, protocol=_protocol(owner_engine, forbid_dirty_runs=False)
    )
    assert _submit(allowed.owner, allowed.exp).status_code == 200


def test_hidden_required_case_blocks_submit(api: Api, fx: Fx, owner_engine: Engine) -> None:
    flow = _flow(api, fx, owner_engine, anonymized=False)
    detail = _detail(flow.owner, flow.exp.id)
    assert detail.submit_check is not None
    assert [i.satisfied for i in detail.submit_check if i.code == "required_cases_visible"] == [
        False
    ]
    assert _err(_submit(flow.owner, flow.exp)) == (409, "conflict")


def test_only_owner_submits(api: Api, fx: Fx, owner_engine: Engine) -> None:
    flow = _flow(api, fx, owner_engine)
    _, other = api.client(Role.ENGINEER)
    assert _err(_submit(other, flow.exp)) == (403, "forbidden")


def test_locked_after_submit(api: Api, fx: Fx, owner_engine: Engine, app_engine: Engine) -> None:
    flow = _flow(api, fx, owner_engine)
    assert _submit(flow.owner, flow.exp).status_code == 200
    assert _err(_post(flow.owner, f"/experiments/{flow.exp.id}/cancel")) == (
        409, "experiment_locked",
    )  # fmt: skip
    assert _err(_submit(flow.owner, flow.exp)) == (409, "experiment_locked")
    comment = {"target_type": "experiment", "target_id": str(flow.exp.id), "body": "hỏi"}
    assert _post(flow.owner, f"/experiments/{flow.exp.id}/comments", comment).status_code == 201
    # Ghi thẳng vào DB (thêm run, sửa trường) cũng bị trigger chặn.
    with app_engine.connect() as conn, pytest.raises(DBAPIError, match="bị khóa"):
        conn.execute(text("UPDATE experiments SET name = 'x' WHERE id = :id"), {"id": flow.exp.id})


def test_submit_emails_active_reviewers_except_owner(
    api: Api, fx: Fx, owner_engine: Engine, app_engine: Engine
) -> None:
    owner_id, owner = api.client(Role.ENGINEER, Role.REVIEWER)
    reviewer_id, _ = api.client(Role.REVIEWER)
    exp = _experiment(owner_engine, fx, owner_id, _protocol(owner_engine))
    assert _submit(owner, exp).status_code == 200
    with Session(app_engine) as s:
        emails = {
            u.id: s.scalar(
                select(func.count())
                .select_from(m.EmailOutbox)
                .where(
                    m.EmailOutbox.to == u.email, m.EmailOutbox.subject.contains(exp_name(s, exp))
                )
            )
            for u in (s.get(m.User, owner_id), s.get(m.User, reviewer_id))
            if u is not None
        }
    assert emails == {owner_id: 0, reviewer_id: 1}


def exp_name(s: Session, exp: Exp) -> str:
    row = s.get(m.Experiment, exp.id)
    assert row is not None
    return row.name


# ---------------------------------------------------------------- tách quyền


def test_engineer_reviewer_cannot_review_own(api: Api, fx: Fx, owner_engine: Engine) -> None:
    owner_id, both = api.client(Role.ENGINEER, Role.REVIEWER)
    exp = _experiment(owner_engine, fx, owner_id, _protocol(owner_engine))
    assert _submit(both, exp).status_code == 200
    waiting = [ReviewQueueItem.model_validate(i) for i in both.get("/reviews").json()]
    assert exp.id not in {i.experiment.id for i in waiting}
    assert _err(_post(both, f"/reviews/{exp.id}/claim")) == (403, "forbidden")


def test_assignee_trigger(api: Api, fx: Fx, owner_engine: Engine, app_engine: Engine) -> None:
    flow = _flow(api, fx, owner_engine)
    assert _submit(flow.owner, flow.exp).status_code == 200
    with app_engine.connect() as conn, pytest.raises(DBAPIError, match="nhận review"):
        conn.execute(
            text(
                "UPDATE experiments SET review_assignee_id = created_by, status = 'in_review'"
                " WHERE id = :id"
            ),
            {"id": flow.exp.id},
        )


def test_claim_release_and_second_claim(api: Api, fx: Fx, owner_engine: Engine) -> None:
    flow = _flow(api, fx, owner_engine)
    assert _submit(flow.owner, flow.exp).status_code == 200
    _, second = api.client(Role.REVIEWER)
    claimed = _post(flow.reviewer, f"/reviews/{flow.exp.id}/claim")
    assert claimed.status_code == 200
    detail = ExperimentDetail.model_validate(claimed.json())
    assert detail.status == ExperimentStatus.IN_REVIEW
    assert detail.review is not None and detail.review.assignee is not None
    assert detail.review.assignee.id == flow.reviewer_id
    assert _err(_post(second, f"/reviews/{flow.exp.id}/claim")) == (409, "conflict")
    assert _err(_post(second, f"/reviews/{flow.exp.id}/release")) == (403, "forbidden")
    case = detail.review.required_cases[0].failure_case_id
    assert _err(_verdict(second, flow.exp, case)) == (403, "forbidden")
    assert _err(_post(second, f"/reviews/{flow.exp.id}/decision", APPROVE)) == (403, "forbidden")
    released = _post(flow.reviewer, f"/reviews/{flow.exp.id}/release")
    assert ExperimentDetail.model_validate(released.json()).status == (
        ExperimentStatus.SUBMITTED_FOR_REVIEW
    )
    assert _post(second, f"/reviews/{flow.exp.id}/claim").status_code == 200


@pytest.mark.parametrize("role", [Role.ENGINEER, Role.ADMIN])
def test_non_reviewer_cannot_decide(api: Api, fx: Fx, owner_engine: Engine, role: Role) -> None:
    flow = _flow(api, fx, owner_engine)
    _, client = api.client(role)
    assert _err(_post(client, f"/reviews/{flow.exp.id}/decision", APPROVE)) == (403, "forbidden")


def test_queue_groups_and_sort(api: Api, fx: Fx, owner_engine: Engine) -> None:
    owner_id, owner = api.client(Role.ENGINEER)
    reviewer_id, reviewer = api.client(Role.REVIEWER)
    protocol = _protocol(owner_engine)
    mild: dict[tuple[str, float], tuple[RunStatus, float | None, str | None]] = {
        ("fgsm", 2): (RunStatus.COMPLETED, 0.1, None),
        ("fgsm", 4): (RunStatus.COMPLETED, 0.2, None),
        ("pgd_linf", 2): (RunStatus.COMPLETED, 0.3, None),
    }
    low = _experiment(owner_engine, fx, owner_id, protocol, runs=mild)
    high = _experiment(owner_engine, fx, owner_id, protocol)
    for exp in (low, high):
        assert _submit(owner, exp).status_code == 200
    waiting = [
        ReviewQueueItem.model_validate(i)
        for i in reviewer.get("/reviews", params={"sort": "max_drop"}).json()
    ]
    ours = [i for i in waiting if i.experiment.id in (low.id, high.id)]
    assert [i.experiment.id for i in ours] == [high.id, low.id]
    assert ours[0].max_relative_drop == pytest.approx(0.9)
    assert ours[0].required_cases_total == 4 and ours[0].required_cases_reviewed == 0
    assert _post(reviewer, f"/reviews/{low.id}/claim").status_code == 200
    mine = reviewer.get("/reviews", params={"status": "mine"}).json()
    assert [ReviewQueueItem.model_validate(i).experiment.id for i in mine] == [low.id]
    assert reviewer_id != owner_id


# ---------------------------------------------------------------- verdict


def _claimed(
    api: Api, fx: Fx, owner_engine: Engine, explanations: dict[str, str] | None = None, **kw: Any
) -> Flow:
    flow = _flow(api, fx, owner_engine, **kw)
    explanations = explanations or {}
    assert _submit(flow.owner, flow.exp, **explanations).status_code == 200
    assert _post(flow.reviewer, f"/reviews/{flow.exp.id}/claim").status_code == 200
    return flow


def test_required_cases_are_top_n_per_attack(api: Api, fx: Fx, owner_engine: Engine) -> None:
    flow = _claimed(api, fx, owner_engine)
    review = _detail(flow.reviewer, flow.exp.id).review
    assert review is not None
    picked = [(c.attack_spec_name, c.severity_score, c.image_id) for c in review.required_cases]
    # fgsm có 2 run (6 case điểm 3, 3, 2, 2, 1, 1): lấy hai case điểm 3, theo image_id.
    assert picked == [
        ("fgsm", 3.0, "000000"),
        ("fgsm", 3.0, "000000"),
        ("pgd_linf", 3.0, "000000"),
        ("pgd_linf", 2.0, "000001"),
    ]
    again = _detail(flow.reviewer, flow.exp.id).review
    assert again is not None and again.required_cases == review.required_cases


def test_verdict_versions(api: Api, fx: Fx, owner_engine: Engine, app_engine: Engine) -> None:
    flow = _claimed(api, fx, owner_engine)
    case = flow.exp.cases["pgd_linf_2"][0]
    first = _verdict(flow.reviewer, flow.exp, case)
    second = _verdict(
        flow.reviewer, flow.exp, case, kind="safety_relevant", severity="critical", mitigation="x"
    )
    assert (first.status_code, second.status_code) == (201, 201)
    assert CaseVerdictView.model_validate(second.json()).version == 2
    history = [CaseVerdictView.model_validate(v) for v in
               flow.owner.get(f"/failure-cases/{case}/verdicts").json()]  # fmt: skip
    assert [v.version for v in history] == [2, 1]
    review = _detail(flow.reviewer, flow.exp.id).review
    assert review is not None
    current = {c.failure_case_id: c.current_verdict for c in review.required_cases}
    verdict = current[case]
    assert verdict is not None and verdict.version == 2
    assert _audit(app_engine, case, "case_verdict.recorded") == 2


def test_safety_relevant_needs_mitigation(api: Api, fx: Fx, owner_engine: Engine) -> None:
    flow = _claimed(api, fx, owner_engine)
    case = flow.exp.cases["fgsm_2"][0]
    response = _verdict(flow.reviewer, flow.exp, case, kind="safety_relevant")
    assert response.status_code == 422


def test_verdict_case_must_belong(api: Api, fx: Fx, owner_engine: Engine) -> None:
    flow = _claimed(api, fx, owner_engine)
    other = _flow(api, fx, owner_engine)
    response = _verdict(flow.reviewer, flow.exp, other.exp.cases["fgsm_2"][0])
    assert _err(response) == (404, "not_found")


# ---------------------------------------------------------------- tiêu chí, quyết định


def test_criteria_in_review(api: Api, fx: Fx, owner_engine: Engine) -> None:
    runs = {**RUNS, ("fgsm", 4): (RunStatus.STOPPED_LIMIT, 0.4, "time")}
    flow = _claimed(api, fx, owner_engine, runs=runs, explanations={"fgsm_4": "hết giờ"})
    review = _detail(flow.reviewer, flow.exp.id).review
    assert review is not None
    assert [c.status for c in review.criteria_results] == [
        CriterionStatus.INCONCLUSIVE,  # fgsm eps 4 dừng do giới hạn
        CriterionStatus.FAIL,  # pgd eps 2: 0.9 > 0.3
    ]


def test_approve_requires_verdicts(api: Api, fx: Fx, owner_engine: Engine) -> None:
    flow = _claimed(api, fx, owner_engine)
    response = _post(flow.reviewer, f"/reviews/{flow.exp.id}/decision", APPROVE)
    assert _err(response) == (409, "checklist_incomplete")
    checklist = ErrorResponse.model_validate(response.json()).error.checklist
    assert checklist is not None
    unmet = [i.code for i in checklist if not i.satisfied]
    assert unmet == [ChecklistCode.REQUIRED_CASES_REVIEWED]


@pytest.mark.parametrize("missing", ["conclusion", "mitigation", "model_verdict"])
def test_approve_missing_fields_is_422(
    api: Api, fx: Fx, owner_engine: Engine, missing: str
) -> None:
    flow = _claimed(api, fx, owner_engine)
    body = {k: v for k, v in APPROVE.items() if k != missing}
    assert _post(flow.reviewer, f"/reviews/{flow.exp.id}/decision", body).status_code == 422


def test_inconclusive_needs_justification(api: Api, fx: Fx, owner_engine: Engine) -> None:
    runs = {**RUNS, ("fgsm", 4): (RunStatus.FAILED, None, "error")}
    flow = _claimed(api, fx, owner_engine, runs=runs, explanations={"fgsm_4": "lỗi"})
    _review_all(flow)
    response = _post(flow.reviewer, f"/reviews/{flow.exp.id}/decision", APPROVE)
    assert _err(response) == (422, "invalid_request")
    body = {**APPROVE, "inconclusive_justification": "fgsm eps 4 lỗi; tiêu chí còn lại đủ"}
    assert _post(flow.reviewer, f"/reviews/{flow.exp.id}/decision", body).status_code == 200


def test_approve_flow(api: Api, fx: Fx, owner_engine: Engine, app_engine: Engine) -> None:
    flow = _claimed(api, fx, owner_engine)
    _review_all(flow)
    response = _post(flow.reviewer, f"/reviews/{flow.exp.id}/decision", APPROVE)
    assert response.status_code == 200, response.text
    detail = ExperimentDetail.model_validate(response.json())
    assert detail.status == ExperimentStatus.APPROVED
    review = detail.review
    assert review is not None and review.decision == ReviewDecision.APPROVE
    assert review.model_verdict == "does_not_meet"  # chấp nhận bài test, model không đạt
    with Session(app_engine) as s:
        row = s.scalars(select(m.Review).where(m.Review.experiment_id == flow.exp.id)).one()
        assert [c["status"] for c in row.criteria_results] == ["pass", "fail"]
        assert all(item["satisfied"] for item in row.checklist)
        owner = s.get(m.User, flow.owner_id)
        assert owner is not None
        mails = s.scalar(
            select(func.count())
            .select_from(m.EmailOutbox)
            .where(m.EmailOutbox.to == owner.email, m.EmailOutbox.subject.contains("chấp nhận"))
        )
    assert mails == 1
    assert _audit(app_engine, flow.exp.id, "review.decided") == 1
    # Trạng thái cuối: không verdict, bình luận, quyết định nào nữa.
    case = flow.exp.cases["fgsm_2"][0]
    assert _err(_verdict(flow.reviewer, flow.exp, case)) == (409, "conflict")
    comment = {"target_type": "experiment", "target_id": str(flow.exp.id), "body": "x"}
    assert _err(_post(flow.owner, f"/experiments/{flow.exp.id}/comments", comment)) == (
        409, "conflict",
    )  # fmt: skip
    assert _err(_post(flow.reviewer, f"/reviews/{flow.exp.id}/decision", APPROVE)) == (
        409, "conflict",
    )  # fmt: skip
    assert _err(_submit(flow.owner, flow.exp)) == (409, "experiment_locked")


@pytest.mark.parametrize(
    ("decision", "status"),
    [
        ("changes_requested", ExperimentStatus.CHANGES_REQUESTED),
        ("reject", ExperimentStatus.REJECTED),
    ],
)
def test_changes_requested_and_reject_need_only_conclusion(
    api: Api, fx: Fx, owner_engine: Engine, decision: str, status: ExperimentStatus
) -> None:
    flow = _claimed(api, fx, owner_engine)
    body = {"decision": decision, "conclusion": "Chạy lại"}
    response = _post(flow.reviewer, f"/reviews/{flow.exp.id}/decision", body)
    assert response.status_code == 200, response.text
    assert ExperimentDetail.model_validate(response.json()).status == status
    if decision == "changes_requested":
        clone = flow.owner.get(f"/experiments/{flow.exp.id}/clone")
        assert clone.status_code == 200
        assert clone.json()["config"]["cloned_from"] == str(flow.exp.id)


def test_decided_rows_blocked_in_db(
    api: Api, fx: Fx, owner_engine: Engine, app_engine: Engine
) -> None:
    flow = _claimed(api, fx, owner_engine)
    body = {"decision": "reject", "conclusion": "Không đại diện"}
    assert _post(flow.reviewer, f"/reviews/{flow.exp.id}/decision", body).status_code == 200
    with app_engine.connect() as conn, pytest.raises(DBAPIError, match="đã có quyết định"):
        conn.execute(
            text(
                "INSERT INTO review_comments (experiment_id, author_id, target_type, target_id,"
                " body) VALUES (:e, :a, 'experiment', :e, 'x')"
            ),
            {"e": flow.exp.id, "a": flow.reviewer_id},
        )


# ---------------------------------------------------------------- bình luận


def test_comment_rules(api: Api, fx: Fx, owner_engine: Engine) -> None:
    flow = _flow(api, fx, owner_engine)
    path = f"/experiments/{flow.exp.id}/comments"
    on_run = {"target_type": "run", "target_id": str(flow.exp.runs["fgsm_2"]), "body": "x"}
    assert _err(_post(flow.owner, path, on_run)) == (409, "conflict")  # chưa gửi duyệt
    assert _submit(flow.owner, flow.exp).status_code == 200
    assert _post(flow.owner, path, on_run).status_code == 201
    other = _flow(api, fx, owner_engine)
    foreign = {"target_type": "run", "target_id": str(other.exp.runs["fgsm_2"]), "body": "x"}
    assert _err(_post(flow.owner, path, foreign)) == (422, "invalid_request")
    on_case = {"target_type": "failure_case", "target_id": str(flow.exp.cases["fgsm_2"][0]),
               "body": "nhãn?"}  # fmt: skip
    assert _post(flow.reviewer, path, on_case).status_code == 201
    _, admin = api.client(Role.ADMIN)
    assert _err(_post(admin, path, on_run)) == (403, "forbidden")
    listed = [ReviewComment.model_validate(c) for c in admin.get(path).json()]
    assert [c.target_type for c in listed] == ["run", "failure_case"]
    detail = _detail(flow.owner, flow.exp.id)
    assert detail.review is not None and detail.review.comments_count == 2


# ---------------------------------------------------------------- audit


def test_audit_full_flow(api: Api, fx: Fx, owner_engine: Engine, app_engine: Engine) -> None:
    runs = {**RUNS, ("fgsm", 4): (RunStatus.FAILED, None, "error")}
    flow = _flow(api, fx, owner_engine, runs=runs)
    assert _submit(flow.owner, flow.exp, fgsm_4="lỗi").status_code == 200
    assert _post(flow.reviewer, f"/reviews/{flow.exp.id}/claim").status_code == 200
    assert _post(flow.reviewer, f"/reviews/{flow.exp.id}/release").status_code == 200
    assert _post(flow.reviewer, f"/reviews/{flow.exp.id}/claim").status_code == 200
    comment = {"target_type": "experiment", "target_id": str(flow.exp.id), "body": "x"}
    assert _post(flow.reviewer, f"/experiments/{flow.exp.id}/comments", comment).status_code == 201
    _review_all(flow)
    body = {**APPROVE, "inconclusive_justification": "fgsm eps 4 lỗi"}
    assert _post(flow.reviewer, f"/reviews/{flow.exp.id}/decision", body).status_code == 200
    eid = flow.exp.id
    assert {
        action: _audit(app_engine, eid, action)
        for action in (
            "experiment.submitted", "review.claimed", "review.released", "review.comment_added",
            "review.decided",
        )
    } == {
        "experiment.submitted": 1, "review.claimed": 2, "review.released": 1,
        "review.comment_added": 1, "review.decided": 1,
    }  # fmt: skip
    assert _audit(app_engine, flow.exp.runs["fgsm_4"], "run_explanation.added") == 1
    with Session(app_engine) as s:
        actors = set(
            s.scalars(
                select(m.AuditLog.actor_id).where(
                    m.AuditLog.entity_id == eid, m.AuditLog.action.like("review.%")
                )
            )
        )
    assert actors == {flow.reviewer_id}
