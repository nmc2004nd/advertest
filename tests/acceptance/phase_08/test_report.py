"""validation.md Phase 8, Report (`test_report.py`)."""

from __future__ import annotations

import hashlib
import io
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy import Engine, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from advertest_contracts.hashing import canonical_json
from advertest_contracts.models import ReportDetail, ReportSnapshot, VerifyInfo
from backend.app.api import deps
from backend.app.db import models as m
from backend.app.main import create_app
from backend.app.reports import service as report_service
from backend.app.storage import Buckets

from .conftest import (
    APPROVE,
    DEV_OPEN,
    P5,
    Flow,
    audit_count,
    detail,
    ok,
    post,
    protocol_body,
    runs_of,
    stores,
    unique,
)

pytestmark = pytest.mark.db
OPENAPI = Path(__file__).resolve().parents[3] / "contracts" / "openapi.json"


def _report_id(flow: Flow, experiment_id: str) -> str:
    report = detail(flow.owner, experiment_id).report
    assert report is not None
    return str(report.id)


def _detail(client: TestClient, report_id: str) -> ReportDetail:
    response = client.get(f"/reports/{report_id}")
    assert response.status_code == 200, response.text
    return ReportDetail.model_validate(response.json())


def _download(client: TestClient, report_id: str, fmt: str) -> tuple[dict[str, Any], bytes]:
    issued: dict[str, Any] = ok(client.get(f"/reports/{report_id}/download?format={fmt}")).json()
    file = client.get(issued["url"])
    assert file.status_code == 200, file.text
    return issued, file.content


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_approve_generates_ready_report_with_valid_snapshot(flow: Flow) -> None:
    experiment_id = flow.approved()
    report = _detail(flow.reviewer, _report_id(flow, experiment_id))
    assert report.report.status == "ready"
    assert report.snapshot is not None
    ReportSnapshot.model_validate(report.snapshot.model_dump(mode="json"))
    assert str(report.snapshot.summary.experiment_id) == experiment_id


def test_hashes_match_stored_files(flow: Flow) -> None:
    report_id = _report_id(flow, flow.approved())
    view = _detail(flow.reviewer, report_id).report
    pdf_issued, pdf = _download(flow.reviewer, report_id, "pdf")
    json_issued, raw = _download(flow.reviewer, report_id, "json")
    assert _sha(pdf) == view.pdf_sha256 == pdf_issued["sha256"]
    assert _sha(raw) == view.json_sha256 == json_issued["sha256"]
    # File JSON là `canonical_json` của snapshot đang hiển thị.
    snapshot = _detail(flow.reviewer, report_id).snapshot
    assert snapshot is not None
    assert raw == canonical_json(snapshot.model_dump(mode="json")).encode()


def test_snapshot_has_every_run_with_reason_and_explanation(
    flow: Flow, fail_first_build: list[str]
) -> None:
    experiment_id = flow.experiment()
    failed = next(r for r in runs_of(flow.owner, experiment_id) if r["status"] == "failed")
    ok(flow.submit(experiment_id, run_explanations={failed["run_id"]: "Hết bộ nhớ GPU"}))
    ok(flow.claim(experiment_id))
    flow.review_all(experiment_id)
    ok(flow.decide(experiment_id, **{**APPROVE, "inconclusive_justification": "Run lỗi do máy"}))
    snapshot = _detail(flow.reviewer, _report_id(flow, experiment_id)).snapshot
    assert snapshot is not None
    in_report = {str(r.run_id): r for r in snapshot.runs}
    assert set(in_report) == {r["run_id"] for r in runs_of(flow.owner, experiment_id)}
    row = in_report[failed["run_id"]]
    assert row.status == "failed" and row.status_reason and row.explanation == "Hết bộ nhớ GPU"


def test_history_lists_related_experiments(flow: Flow) -> None:
    main = flow.in_review()
    completed = flow.experiment()  # cùng protocol, không gửi duyệt
    cancelled = flow.experiment(run=False)
    ok(post(flow.owner, f"/experiments/{cancelled}/cancel"))
    dev = flow.experiment(protocol_id=DEV_OPEN, run=False)
    other_model = flow.experiment(
        attacks=[P5.attack("fog", [1.0])], protocol_id=DEV_OPEN, gradient=False, run=False
    )
    flow.review_all(main)
    flow.api.clock.advance(60)  # quyết định sau khi các experiment trên được tạo
    ok(flow.decide(main, **APPROVE))
    snapshot = _detail(flow.reviewer, _report_id(flow, main)).snapshot
    assert snapshot is not None
    related = {str(x.id): x for x in snapshot.history.related_experiments}
    assert {completed, cancelled, dev} <= set(related)
    assert related[completed].status == "completed" and related[cancelled].status == "cancelled"
    assert related[dev].dev is True and related[completed].dev is False
    assert other_model not in related and main not in related
    actions = [e.action for e in snapshot.history.timeline]
    assert actions[0] == "experiment.submitted" and actions[-1] == "review.decided"


def test_mandatory_notes_and_anonymized_cases(flow: Flow) -> None:
    snapshot = _detail(flow.reviewer, _report_id(flow, flow.approved())).snapshot
    assert snapshot is not None
    notes = {n.code: n.text for n in snapshot.notes}
    assert {"test_environment_only", "input_space", "anonymization"} <= set(notes)
    # eps tính trên ảnh letterbox dạng float, không lượng tử 8-bit.
    assert "letterbox" in notes["input_space"] and "float" in notes["input_space"]
    assert "8-bit" in notes["input_space"]
    assert "git_dirty" not in notes
    assert snapshot.reviewed_cases
    assert all(c.anonymization.applied for c in snapshot.reviewed_cases)


def test_git_dirty_note_when_protocol_allows(flow: Flow, dirty_tree: None) -> None:
    protocol = ok(
        post(
            flow.reviewer,
            "/protocols",
            {"name": unique("p"), "body": protocol_body(forbid_dirty_runs=False)},
        )
    ).json()
    experiment_id = flow.experiment(protocol_id=protocol["id"])
    ok(flow.submit(experiment_id))
    ok(flow.claim(experiment_id))
    flow.review_all(experiment_id)
    ok(flow.decide(experiment_id, **APPROVE))
    snapshot = _detail(flow.reviewer, _report_id(flow, experiment_id)).snapshot
    assert snapshot is not None
    assert "git_dirty" in {n.code for n in snapshot.notes}
    assert all(r.git_dirty for r in snapshot.reproducibility)


def test_pdf_footer_on_every_page(flow: Flow) -> None:
    report_id = _report_id(flow, flow.approved())
    _, pdf = _download(flow.reviewer, report_id, "pdf")
    pages = PdfReader(io.BytesIO(pdf)).pages
    assert len(pages) >= 2
    for page in pages:
        content = page.extract_text()
        assert report_id in content and "BẢN CHÍNH THỨC" in content


def test_download_twice_same_hash_audited(flow: Flow, app_engine: Engine) -> None:
    report_id = _report_id(flow, flow.approved())
    first, a = _download(flow.reviewer, report_id, "pdf")
    second, b = _download(flow.reviewer, report_id, "pdf")
    assert _sha(a) == _sha(b) == first["sha256"] == second["sha256"]
    assert audit_count(app_engine, "report.downloaded", report_id) == 2


@pytest.mark.parametrize("role", ["engineer", "admin"])
def test_only_report_export_downloads(flow: Flow, role: str) -> None:
    report_id = _report_id(flow, flow.approved())
    client = flow.owner if role == "engineer" else flow.api.admin()
    assert client.get(f"/reports/{report_id}/download?format=pdf").status_code == 403
    viewed = client.get(f"/reports/{report_id}")
    assert viewed.status_code == 200
    assert "/reports/files/" not in viewed.text  # không có URL tải
    assert post(client, f"/reports/{report_id}/regenerate").status_code == 403


def test_failure_then_regenerate_keeps_id(
    flow: Flow, buckets: Buckets, report_stores: dict[str, Any], app_engine: Engine
) -> None:
    def broken(key: str, data: bytes) -> None:
        raise RuntimeError("Ép lỗi khi lưu report")

    report_stores["current"] = report_service.Stores(
        read_artifact=buckets.artifacts.get, put=broken, get=buckets.reports.get
    )
    experiment_id = flow.approved()
    report = detail(flow.owner, experiment_id).report
    assert report is not None and report.status == "failed"
    assert detail(flow.owner, experiment_id).status == "approved"
    with Session(app_engine) as session:
        row = session.get(m.Report, report.id)
        assert row is not None and row.attempts == 3
    assert audit_count(app_engine, "report.generation_failed", report.id) == 1
    report_stores["current"] = stores(buckets)
    regenerated = ok(post(flow.reviewer, f"/reports/{report.id}/regenerate")).json()
    assert regenerated["id"] == str(report.id)
    after = _detail(flow.reviewer, str(report.id)).report
    assert after.status == "ready" and after.id == report.id


def test_ready_report_is_immutable(flow: Flow, app_engine: Engine) -> None:
    report_id = _report_id(flow, flow.approved())
    with app_engine.begin() as conn, pytest.raises(DBAPIError):
        conn.execute(
            text("UPDATE reports SET pdf_sha256 = :h WHERE id = :id"),
            {"h": "0" * 64, "id": report_id},
        )
    with app_engine.begin() as conn, pytest.raises(DBAPIError):
        conn.execute(text("DELETE FROM reports WHERE id = :id"), {"id": report_id})


@pytest.fixture
def startup_env(monkeypatch: pytest.MonkeyPatch, cli_env: dict[str, str]) -> Iterator[None]:
    """Biến môi trường của bản triển khai trỏ vào DB và MinIO của test (lifespan đọc chúng)."""
    for name, value in cli_env.items():
        monkeypatch.setenv(name, value)
    deps.get_sessionmaker.cache_clear()
    deps.get_storage.cache_clear()
    yield
    deps.get_sessionmaker.cache_clear()
    deps.get_storage.cache_clear()


def test_generating_report_resumed_on_startup(
    flow: Flow,
    buckets: Buckets,
    report_stores: dict[str, Any],
    owner_engine: Engine,
    startup_env: None,
) -> None:
    def broken(key: str, data: bytes) -> None:
        raise RuntimeError("API dừng giữa chừng")

    report_stores["current"] = report_service.Stores(
        read_artifact=buckets.artifacts.get, put=broken, get=buckets.reports.get
    )
    experiment_id = flow.approved()
    report = detail(flow.owner, experiment_id).report
    assert report is not None
    # Giả lập tác vụ nền bị ngắt khi đang sinh: report còn ở `generating`.
    with Session(owner_engine) as session, session.begin():
        session.execute(
            update(m.Report).where(m.Report.id == report.id).values(status="generating")
        )
    with TestClient(create_app()):
        pass  # lifespan: sinh tiếp report `generating` rồi mới đóng
    after = _detail(flow.reviewer, str(report.id)).report
    assert after.status == "ready"


def test_no_endpoint_creates_report_outside_approve() -> None:
    """Report chỉ được tạo trong quyết định `approve`: không có endpoint POST nào khác tạo report;
    `regenerate` chỉ chạy lại report `failed` đã có."""
    paths: dict[str, dict[str, Any]] = json.loads(OPENAPI.read_text())["paths"]
    posts = {p for p, methods in paths.items() if p.startswith("/reports") and "post" in methods}
    assert posts == {"/reports/{report_id}/regenerate"}


def test_regenerate_rejects_non_failed(flow: Flow) -> None:
    report_id = _report_id(flow, flow.approved())
    assert post(flow.reviewer, f"/reports/{report_id}/regenerate").status_code == 409


def test_verify_is_public_and_minimal(flow: Flow) -> None:
    report_id = _report_id(flow, flow.approved())
    anonymous = flow.api.client()
    response = anonymous.get(f"/verify/{report_id}")
    assert response.status_code == 200, response.text
    info = VerifyInfo.model_validate(response.json())
    assert set(response.json()) == {"report_id", "issued_at", "json_sha256", "pdf_sha256"}
    view = _detail(flow.reviewer, report_id).report
    assert (info.pdf_sha256, info.json_sha256) == (view.pdf_sha256, view.json_sha256)
    assert anonymous.get(f"/verify/{UUID(int=0)}").status_code == 404
