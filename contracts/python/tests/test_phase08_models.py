"""Contract Phase 8: protocol, review, report (requirements.md Phase 8, mục Data / Fields, các
quyết định chốt ở kickoff và Group 0)."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from advertest_contracts.enums import (
    CriterionStatus,
    ErrorCode,
    ExperimentStatus,
    ProtocolStatus,
    ReportStatus,
    Role,
)
from advertest_contracts.hashing import sha256_of
from advertest_contracts.models import (
    CaseVerdictInput,
    ErrorResponse,
    ExperimentDetail,
    ProtocolBody,
    ProtocolCreate,
    ProtocolView,
    ReportDetail,
    ReportSnapshot,
    ReportView,
    ReviewComment,
    ReviewDecisionInput,
    ReviewQueueItem,
)
from advertest_contracts.permissions import ROLE_PERMISSIONS, Permission

MOCKS = Path(__file__).resolve().parents[2] / "mocks"


def mock(schema: str, name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((MOCKS / schema / f"{name}.json").read_text())
    return data


def mocks(schema: str) -> list[dict[str, Any]]:
    return [json.loads(p.read_text()) for p in sorted((MOCKS / schema).glob("*.json"))]


def invalid(model: type[BaseModel], data: dict[str, Any], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        model.model_validate(data)


# ---------------------------------------------------------------- ProtocolBody


def test_protocol_body_defaults() -> None:
    body = ProtocolBody.model_validate(mock("protocol_body", "default"))
    assert body.schema_version == 2
    assert body.cases_to_review_per_attack == 5
    assert body.forbid_dirty_runs is True
    search = ProtocolBody.model_validate(mock("protocol_body", "search"))
    assert search.required_attacks[1].search is not None
    assert search.required_attacks[1].search.min_bootstrap_samples == 200


def test_protocol_body_rejects_old_schema() -> None:
    old = {**mock("protocol_body", "default"), "review_severity_threshold": "major"}
    invalid(ProtocolBody, old, "review_severity_threshold")
    invalid(ProtocolBody, {**mock("protocol_body", "default"), "schema_version": 1}, "2")


def test_protocol_body_rejects_duplicate_attack() -> None:
    body = mock("protocol_body", "default")
    body["required_attacks"].append(copy.deepcopy(body["required_attacks"][0]))
    invalid(ProtocolBody, body, "không được trùng attack_spec_name")


@pytest.mark.parametrize(
    ("change", "match"),
    [
        ({"attack_spec_name": "fog"}, "không có trong required_attacks"),
        ({"level": 16}, "level bắt buộc"),
        ({"kind": "min_breaking_point"}, "chỉ dùng với attack tìm ngưỡng"),
    ],
)
def test_max_drop_criterion_rules(change: dict[str, Any], match: str) -> None:
    body = mock("protocol_body", "default")
    body["pass_criteria"][0].update(change)
    invalid(ProtocolBody, body, match)


@pytest.mark.parametrize(
    ("change", "match"),
    [
        ({"kind": "max_drop_at_level"}, "chỉ dùng với attack quét lưới"),
        ({"threshold": 0.3}, "cùng threshold_kind, threshold, class_filter"),
        ({"class_filter": "person"}, "cùng threshold_kind, threshold, class_filter"),
        ({"level": 0}, "lo < level ≤ hi"),
        ({"level": 33}, "lo < level ≤ hi"),
    ],
)
def test_min_breaking_point_rules(change: dict[str, Any], match: str) -> None:
    body = mock("protocol_body", "search")
    body["pass_criteria"][1].update(change)
    invalid(ProtocolBody, body, match)


def test_min_breaking_point_level_may_equal_hi() -> None:
    body = mock("protocol_body", "search")
    body["pass_criteria"][1]["level"] = 32
    ProtocolBody.model_validate(body)


def test_required_attack_mode_and_ranges() -> None:
    body = mock("protocol_body", "search")
    attack = body["required_attacks"][1]
    invalid(ProtocolBody, {**body, "required_attacks": [{**attack, "mode": "grid"}]}, "grid")
    bad = copy.deepcopy(body)
    bad["required_attacks"][1]["search"].update(lo=4, hi=4)
    invalid(ProtocolBody, bad, "lo phải nhỏ hơn hi")
    bad = copy.deepcopy(body)
    bad["required_attacks"][1]["search"]["max_tol"] = 32
    invalid(ProtocolBody, bad, "max_tol")
    bad = copy.deepcopy(body)
    bad["required_attacks"][0]["grid"]["levels"] = [2, 2]
    invalid(ProtocolBody, bad, "không được trùng")


def test_dev_open_body_is_empty_but_create_requires_content() -> None:
    dev = ProtocolBody.model_validate(mock("protocol_body", "dev_open"))
    assert dev.required_attacks == [] and dev.pass_criteria == []
    invalid(ProtocolCreate, {"name": "x", "body": dev.model_dump()}, "attack bắt buộc")
    no_criteria = {**mock("protocol_body", "default"), "pass_criteria": []}
    invalid(ProtocolCreate, {"name": "x", "body": no_criteria}, "tiêu chí")


def test_protocol_view_hash_and_creator() -> None:
    for data in mocks("protocol_view"):
        view = ProtocolView.model_validate(data)
        assert view.body_sha256 == sha256_of(view.body)
    active = mock("protocol_view", "kitti_baseline_v2_active")
    invalid(ProtocolView, {**active, "body_sha256": "0" * 64}, "body_sha256")
    invalid(ProtocolView, {**active, "created_by": None}, "created_by")
    statuses = {ProtocolView.model_validate(d).status for d in mocks("protocol_view")}
    assert statuses == set(ProtocolStatus)


# ---------------------------------------------------------------- review


def test_case_verdict_safety_relevant_needs_mitigation() -> None:
    data = mock("case_verdict_input", "safety_relevant")
    invalid(CaseVerdictInput, {**data, "mitigation": None}, "mitigation")
    CaseVerdictInput.model_validate(mock("case_verdict_input", "annotation_issue"))


def test_review_decision_input_rules() -> None:
    approve = mock("review_decision_input", "approve")
    invalid(ReviewDecisionInput, {**approve, "model_verdict": None}, "model_verdict")
    invalid(ReviewDecisionInput, {**approve, "mitigation": None}, "mitigation")
    invalid(ReviewDecisionInput, {**approve, "conclusion": "   "}, "conclusion")
    # changes_requested, reject chỉ cần conclusion.
    ReviewDecisionInput.model_validate(mock("review_decision_input", "changes_requested"))
    reject = mock("review_decision_input", "reject")
    invalid(
        ReviewDecisionInput, {k: v for k, v in reject.items() if k != "conclusion"}, "conclusion"
    )


def test_review_comment_experiment_target() -> None:
    comment = mock("review_comment", "experiment")
    invalid(ReviewComment, {**comment, "target_id": comment["id"]}, "target_id")


def _details() -> dict[str, dict[str, Any]]:
    return {p.stem: json.loads(p.read_text()) for p in (MOCKS / "experiment_detail").glob("*.json")}


def test_experiment_detail_mocks_cover_review_states() -> None:
    details = [ExperimentDetail.model_validate(d) for d in _details().values()]
    statuses = {d.status for d in details if d.review is not None}
    assert statuses == {
        ExperimentStatus.SUBMITTED_FOR_REVIEW,
        ExperimentStatus.IN_REVIEW,
        ExperimentStatus.APPROVED,
        ExperimentStatus.CHANGES_REQUESTED,
        ExperimentStatus.REJECTED,
    }
    criteria = {r.status for d in details if d.review for r in d.review.criteria_results}
    assert criteria == set(CriterionStatus)
    checklists = {all(item.satisfied for item in d.review.checklist) for d in details if d.review}
    assert checklists == {True, False}
    reports = {d.report.status for d in details if d.report is not None}
    assert reports == set(ReportStatus)
    submit = {all(i.satisfied for i in d.submit_check) for d in details if d.submit_check}
    assert submit == {True, False}


@pytest.mark.parametrize(
    ("name", "change", "match"),
    [
        ("review_in_review_partial", {"status": "completed"}, "review có khi và chỉ khi"),
        ("review_submitted_waiting", {"status": "in_review"}, "assignee"),
        ("review_changes_requested", {"status": "rejected"}, "decision không khớp"),
        ("review_in_review_partial", {"submit_check": []}, "submit_check chỉ có"),
    ],
)
def test_experiment_detail_review_consistency(
    name: str, change: dict[str, Any], match: str
) -> None:
    invalid(ExperimentDetail, {**_details()[name], **change}, match)


def test_reviewer_cannot_be_owner() -> None:
    data = _details()["review_in_review_partial"]
    data["review"]["assignee"] = data["owner"]
    invalid(ExperimentDetail, data, "người nhận review")


def test_report_only_when_approved() -> None:
    data = _details()["review_approved_report_ready"]
    report = data["report"]
    invalid(
        ExperimentDetail,
        {**_details()["review_in_review_ready"], "report": report},
        "report chỉ có",
    )


def test_review_queue_rejects_unsubmitted() -> None:
    item = mock("review_queue_item", "waiting")
    item["experiment"]["status"] = "completed"
    invalid(ReviewQueueItem, item, "đã gửi duyệt")


# ---------------------------------------------------------------- report


def test_report_view_hashes_only_when_ready() -> None:
    ready = mock("report_view", "ready")
    invalid(ReportView, {**ready, "pdf_sha256": None}, "ready")
    failed = mock("report_view", "failed")
    invalid(ReportView, {**failed, "json_sha256": "0" * 64}, "ready")


def test_report_snapshot_rules() -> None:
    snap = mock("report_snapshot", "approved_grid")
    ReportSnapshot.model_validate(snap)
    notes = [n for n in snap["notes"] if n["code"] != "test_environment_only"]
    invalid(ReportSnapshot, {**snap, "notes": notes}, "lưu ý bắt buộc")
    case = copy.deepcopy(snap["reviewed_cases"][0])
    case["anonymization"]["applied"] = False
    invalid(ReportSnapshot, {**snap, "reviewed_cases": [case]}, "đã làm mờ")
    invalid(
        ReportSnapshot,
        {**snap, "reproducibility": snap["reproducibility"][::-1]},
        "reproducibility",
    )
    invalid(ReportSnapshot, {**snap, "runs": [*snap["runs"], snap["runs"][0]]}, "không được trùng")
    owner_approves = copy.deepcopy(snap)
    owner_approves["summary"]["approved_by"] = snap["summary"]["owner"]
    invalid(ReportSnapshot, owner_approves, "người duyệt")


def test_report_snapshot_git_dirty_note() -> None:
    dirty = mock("report_snapshot", "search_dirty")
    ReportSnapshot.model_validate(dirty)
    no_note = [n for n in dirty["notes"] if n["code"] != "git_dirty"]
    invalid(ReportSnapshot, {**dirty, "notes": no_note}, "git_dirty")
    forbidden = copy.deepcopy(dirty)
    forbidden["configuration"]["protocol"]["body"]["forbid_dirty_runs"] = True
    forbidden["configuration"]["protocol"]["body_sha256"] = sha256_of(
        ProtocolBody.model_validate(forbidden["configuration"]["protocol"]["body"])
    )
    invalid(ReportSnapshot, forbidden, "forbid_dirty_runs")


def test_report_snapshot_hash_is_stable() -> None:
    snap = ReportSnapshot.model_validate(mock("report_snapshot", "approved_grid"))
    again = ReportSnapshot.model_validate_json(snap.model_dump_json())
    assert sha256_of(snap) == sha256_of(again)


def test_report_detail_snapshot_iff_ready() -> None:
    ready = mock("report_detail", "ready")
    invalid(ReportDetail, {**ready, "snapshot": None}, "snapshot")
    failed = mock("report_detail", "failed")
    invalid(ReportDetail, {**failed, "snapshot": ready["snapshot"]}, "snapshot")


# ---------------------------------------------------------------- lỗi, quyền


def test_error_body_carries_compliance_and_checklist() -> None:
    compliance = mock("experiment_detail", "review_completed_ready_to_submit")["compliance"]
    body = {
        "error": {
            "code": "not_compliant",
            "message": "Không tuân thủ protocol",
            "compliance": compliance,
        }
    }
    assert ErrorResponse.model_validate(body).error.code == ErrorCode.NOT_COMPLIANT
    checklist = mock("experiment_detail", "review_in_review_partial")["review"]["checklist"]
    body = {
        "error": {
            "code": "checklist_incomplete",
            "message": "Chưa đủ điều kiện",
            "checklist": checklist,
        }
    }
    assert ErrorResponse.model_validate(body).error.checklist is not None
    # Lỗi cũ không có hai trường này (bỏ khỏi body khi null).
    dumped = ErrorResponse.model_validate(mock("error_response", "not_implemented")).model_dump(
        mode="json", exclude_none=True
    )
    assert set(dumped["error"]) == {"code", "message"}


def test_review_comment_permission() -> None:
    assert Permission.REVIEW_COMMENT in ROLE_PERMISSIONS[Role.ENGINEER]
    assert Permission.REVIEW_COMMENT in ROLE_PERMISSIONS[Role.REVIEWER]
    assert Permission.REVIEW_COMMENT not in ROLE_PERMISSIONS[Role.ADMIN]


@pytest.mark.parametrize(
    ("code", "change"),
    [
        ("anonymization", None),
        ("excluded_classes", None),
        ("occlusion_stress", {"kind": "occlusion"}),
        ("patch_fixed_position", {"requires_training": True}),
    ],
)
def test_report_snapshot_conditional_notes(code: str, change: dict[str, Any] | None) -> None:
    """Lưu ý bắt buộc theo nội dung (review Group 0 #1): case đã review → phương pháp làm mờ;
    class bị loại; occlusion; patch."""
    snap = mock("report_snapshot", "approved_grid")
    snap["notes"] = [n for n in snap["notes"] if n["code"] != code]
    if change is not None:
        snap["configuration"]["attack_specs"][0].update(change)
    invalid(ReportSnapshot, snap, code)


def test_report_snapshot_conditional_notes_not_needed() -> None:
    snap = mock("report_snapshot", "search_dirty")
    assert snap["reviewed_cases"] == []
    snap["notes"] = [
        n
        for n in snap["notes"]
        if n["code"] not in {"anonymization", "occlusion_stress", "patch_fixed_position"}
    ]
    ReportSnapshot.model_validate(snap)
