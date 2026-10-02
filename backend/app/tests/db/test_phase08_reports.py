"""Phase 8 Group 3: sinh report, tải, xác minh (plan task 19-23; validation.md mục test_report và
phần report của test_audit_phase08)."""

from __future__ import annotations

import hashlib
import io
import json
import uuid
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy import Engine, func, select, update
from sqlalchemy.orm import Session, sessionmaker

from advertest_contracts.enums import (
    ExperimentStatus,
    ReportNoteCode,
    ReportStatus,
    Role,
    RunStatus,
)
from advertest_contracts.hashing import canonical_json
from advertest_contracts.models import (
    ExperimentDetail,
    ReportDetail,
    ReportDownload,
    ReportView,
    VerifyInfo,
)
from backend.app.api import public
from backend.app.db import models as m
from backend.app.reports import service as report_service
from backend.app.storage import Buckets

from .test_auth_api import _login, _user
from .test_experiment_api import DEV_OPEN, Api, Fx, _post, api, env, fx, world
from .test_phase08_reviews import (
    APPROVE,
    RUNS,
    Exp,
    _experiment,
    _protocol,
    _submit,
    _verdict,
)
from .test_worker_services import T0

pytestmark = pytest.mark.db
OPENAPI = Path(__file__).resolve().parents[4] / "contracts" / "openapi.json"
__all__ = ["api", "env", "fx", "world"]
PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
    b"\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00\xc9\xfe\x92\xef"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _stores(buckets: Buckets, fail: bool = False) -> report_service.Stores:
    def put(key: str, data: bytes) -> None:
        if fail:
            raise RuntimeError("ép lỗi khi lưu report")
        buckets.reports.put(key, data)

    return report_service.Stores(
        read_artifact=buckets.artifacts.get, put=put, get=buckets.reports.get
    )


def _client(api: Api, stores: report_service.Stores, *roles: Role) -> tuple[uuid.UUID, TestClient]:
    user_id, email = _user(api.env.engine, roles=roles or (Role.ENGINEER,))
    client = api.env.client()
    app: Any = client.app
    app.dependency_overrides[public.get_report_stores] = lambda: stores
    assert _login(client, email).status_code == 200
    return user_id, client


def _with_thumbnails(owner_engine: Engine, buckets: Buckets, exp: Exp) -> None:
    """Failure case của `_experiment` chưa có ảnh: thêm khóa và thumbnail đã làm mờ."""
    with Session(owner_engine) as s, s.begin():
        for case_ids in exp.cases.values():
            for case_id in case_ids:
                case = s.get(m.FailureCase, case_id)
                assert case is not None
                prefix = f"runs/{case.run_id}/cases/{case.id}"
                keys = {
                    "clean_png": f"{prefix}/clean.png",
                    "adversarial_png": f"{prefix}/adv.png",
                    "perturbation_png": f"{prefix}/noise.png",
                    "adversarial_thumb": f"{prefix}/adv_thumb.png",
                }
                buckets.artifacts.put(keys["adversarial_thumb"], PNG)
                case.artifacts = keys


@pytest.fixture
def approved(
    api: Api, fx: Fx, owner_engine: Engine, buckets: Buckets
) -> Callable[..., tuple[Exp, ExperimentDetail, TestClient, TestClient]]:
    def make(
        *, stores: report_service.Stores | None = None, **kw: Any
    ) -> tuple[Exp, ExperimentDetail, TestClient, TestClient]:
        stores = stores or _stores(buckets)
        owner_id, owner = _client(api, stores, Role.ENGINEER)
        _, reviewer = _client(api, stores, Role.REVIEWER)
        protocol = kw.pop("protocol", None) or _protocol(owner_engine)
        explanations = kw.pop("explanations", {})
        exp = _experiment(owner_engine, fx, owner_id, protocol, **kw)
        _with_thumbnails(owner_engine, buckets, exp)
        assert _submit(owner, exp, **explanations).status_code == 200
        assert _post(reviewer, f"/reviews/{exp.id}/claim").status_code == 200
        detail = ExperimentDetail.model_validate(reviewer.get(f"/experiments/{exp.id}").json())
        assert detail.review is not None
        for case in detail.review.required_cases:
            assert _verdict(reviewer, exp, case.failure_case_id).status_code == 201
        # Experiment tạo lúc T0; duyệt sau đó (lịch sử chỉ gồm experiment tạo trước khi duyệt).
        api.env.clock.now = T0 + timedelta(minutes=5)
        body = {**APPROVE, "inconclusive_justification": "Run lỗi; tiêu chí khác đủ"}
        response = _post(reviewer, f"/reviews/{exp.id}/decision", body)
        assert response.status_code == 200, response.text
        # BackgroundTasks của TestClient chạy xong trước khi trả về.
        after = ExperimentDetail.model_validate(owner.get(f"/experiments/{exp.id}").json())
        return exp, after, owner, reviewer

    return make


def _report(detail: ExperimentDetail) -> ReportView:
    assert detail.report is not None
    return detail.report


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


# ---------------------------------------------------------------- sinh report


def test_approve_generates_ready_report(
    approved: Any, buckets: Buckets, app_engine: Engine
) -> None:
    _, detail, owner, _ = approved()
    assert detail.status == ExperimentStatus.APPROVED
    report = _report(detail)
    assert report.status == ReportStatus.READY
    got = ReportDetail.model_validate(owner.get(f"/reports/{report.id}").json())
    assert got.snapshot is not None and got.snapshot.report_id == report.id
    with Session(app_engine) as s:
        row = s.get(m.Report, report.id)
        assert row is not None and row.json_key and row.pdf_key
        json_bytes = buckets.reports.get(row.json_key)
        pdf_bytes = buckets.reports.get(row.pdf_key)
    assert hashlib.sha256(json_bytes).hexdigest() == report.json_sha256
    assert hashlib.sha256(pdf_bytes).hexdigest() == report.pdf_sha256
    assert json_bytes.decode() == canonical_json(got.snapshot)
    assert _audit(app_engine, report.id, "report.generated") == 1
    listed = [ReportView.model_validate(r) for r in owner.get("/reports").json()]
    assert report.id in {r.id for r in listed}


def test_snapshot_has_every_run_with_reason_and_explanation(approved: Any) -> None:
    runs = {
        **RUNS,
        ("fgsm", 4): (RunStatus.FAILED, None, "error"),
        ("pgd_linf", 2): (RunStatus.STOPPED_LIMIT, 0.5, "time"),
        ("pgd_linf", 4): (RunStatus.SKIPPED, 0.95, "cached"),
        ("pgd_linf", 8): (RunStatus.CANCELLED, None, "cancelled"),
    }
    explanations = {"fgsm_4": "Hết bộ nhớ", "pgd_linf_2": "Hết giờ", "pgd_linf_8": "Đã hủy"}
    exp, detail, owner, _ = approved(runs=runs, explanations=explanations)
    snap = ReportDetail.model_validate(owner.get(f"/reports/{_report(detail).id}").json()).snapshot
    assert snap is not None
    by_id = {r.run_id: r for r in snap.runs}
    assert set(by_id) == set(exp.runs.values())
    assert {r.status for r in snap.runs} == {
        RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.STOPPED_LIMIT, RunStatus.SKIPPED,
        RunStatus.CANCELLED,
    }  # fmt: skip
    failed = by_id[exp.runs["fgsm_4"]]
    assert failed.status_reason is not None and failed.explanation == "Hết bộ nhớ"
    assert [r.run_id for r in snap.reproducibility] == [r.run_id for r in snap.runs]


def test_history_lists_related_experiments(
    approved: Any, api: Api, fx: Fx, owner_engine: Engine, buckets: Buckets
) -> None:
    """Kickoff Phase 8: cùng protocol (mọi trạng thái) và dev-open, cùng model, dataset version."""
    owner_id, _ = _client(api, _stores(buckets))
    protocol = _protocol(owner_engine)
    other_completed = _experiment(owner_engine, fx, owner_id, protocol)
    other_cancelled = _experiment(
        owner_engine, fx, owner_id, protocol, status=ExperimentStatus.CANCELLED
    )
    dev = _experiment(owner_engine, fx, owner_id, DEV_OPEN)
    other_model = _experiment(owner_engine, fx, owner_id, protocol)
    with Session(owner_engine) as s, s.begin():  # khác model version: không thuộc lịch sử
        s.execute(
            update(m.Experiment)
            .where(m.Experiment.id == other_model.id)
            .values(model_version_id=fx.nograd_model, class_mapping_id=fx.nograd_mapping)
        )
    exp, detail, owner, _ = approved(protocol=protocol)
    snap = ReportDetail.model_validate(owner.get(f"/reports/{_report(detail).id}").json()).snapshot
    assert snap is not None
    related = {e.id: e for e in snap.history.related_experiments}
    assert {other_completed.id, other_cancelled.id, dev.id} <= set(related)
    assert other_model.id not in related and exp.id not in related
    assert related[dev.id].dev and not related[other_completed.id].dev
    assert related[other_cancelled.id].status == ExperimentStatus.CANCELLED
    actions = [t.action for t in snap.history.timeline]
    assert actions == ["experiment.submitted", "review.claimed", "review.decided"]


def test_notes_and_anonymized_cases(approved: Any, owner_engine: Engine) -> None:
    allow = _protocol(owner_engine, forbid_dirty_runs=False)
    _, detail, owner, _ = approved(protocol=allow, dirty=True)
    snap = ReportDetail.model_validate(owner.get(f"/reports/{_report(detail).id}").json()).snapshot
    assert snap is not None
    codes = {n.code for n in snap.notes}
    assert {
        ReportNoteCode.TEST_ENVIRONMENT_ONLY, ReportNoteCode.INPUT_SPACE,
        ReportNoteCode.ANONYMIZATION, ReportNoteCode.GIT_DIRTY,
    } <= codes  # fmt: skip
    input_space = next(n.text for n in snap.notes if n.code == ReportNoteCode.INPUT_SPACE)
    assert "letterbox" in input_space and "8-bit" in input_space
    assert snap.reviewed_cases and all(c.anonymization.applied for c in snap.reviewed_cases)
    assert all(c.required for c in snap.reviewed_cases)


def test_pdf_footer_on_every_page(approved: Any, buckets: Buckets, app_engine: Engine) -> None:
    _, detail, _, _ = approved()
    report = _report(detail)
    with Session(app_engine) as s:
        row = s.get(m.Report, report.id)
        assert row is not None and row.pdf_key is not None
        pdf = PdfReader(io.BytesIO(buckets.reports.get(row.pdf_key)))
    assert len(pdf.pages) >= 2
    for page in pdf.pages:
        text = " ".join((page.extract_text() or "").split())
        assert "BẢN CHÍNH THỨC" in text and str(report.id) in text.replace(" ", "")


# ---------------------------------------------------------------- tải, quyền


def test_download_twice_same_hash_and_audited(
    approved: Any, api: Api, buckets: Buckets, app_engine: Engine
) -> None:
    _, detail, _, reviewer = approved()
    report = _report(detail)
    _, other_reviewer = _client(api, _stores(buckets), Role.REVIEWER)
    hashes = []
    for client in (reviewer, other_reviewer):
        response = client.get(f"/reports/{report.id}/download", params={"format": "pdf"})
        assert response.status_code == 200, response.text
        link = ReportDownload.model_validate(response.json())
        assert link.sha256 == report.pdf_sha256
        file = client.get(link.url)
        assert file.status_code == 200 and file.headers["content-type"] == "application/pdf"
        hashes.append(hashlib.sha256(file.content).hexdigest())
    assert hashes == [report.pdf_sha256, report.pdf_sha256]
    json_link = ReportDownload.model_validate(
        reviewer.get(f"/reports/{report.id}/download", params={"format": "json"}).json()
    )
    data = reviewer.get(json_link.url).content
    assert hashlib.sha256(data).hexdigest() == report.json_sha256
    assert json.loads(data)["report_id"] == str(report.id)
    assert _audit(app_engine, report.id, "report.downloaded") == 3


def test_file_token_rules(approved: Any) -> None:
    _, detail, _, reviewer = approved()
    link = ReportDownload.model_validate(
        reviewer.get(f"/reports/{_report(detail).id}/download", params={"format": "pdf"}).json()
    )
    token = link.url.rsplit("/", 1)[1]
    tampered = token[:-2] + ("AA" if not token.endswith("AA") else "BB")
    assert reviewer.get(f"/reports/files/{tampered}").status_code == 404
    assert reviewer.get("/reports/files/khong-hop-le").status_code == 404


@pytest.mark.parametrize("role", [Role.ENGINEER, Role.ADMIN])
def test_only_report_export_downloads(
    approved: Any, api: Api, buckets: Buckets, role: Role
) -> None:
    _, detail, _, reviewer = approved()
    report = _report(detail)
    _, client = _client(api, _stores(buckets), role)
    response = client.get(f"/reports/{report.id}/download", params={"format": "pdf"})
    assert response.status_code == 403
    link = ReportDownload.model_validate(
        reviewer.get(f"/reports/{report.id}/download", params={"format": "pdf"}).json()
    )
    assert client.get(link.url).status_code == 403
    seen = client.get(f"/reports/{report.id}")
    assert seen.status_code == 200
    assert "url" not in json.dumps(seen.json()["report"])


# ---------------------------------------------------------------- lỗi, sinh lại, xác minh


def test_failure_then_regenerate_keeps_id(
    approved: Any, api: Api, buckets: Buckets, app_engine: Engine
) -> None:
    _, detail, owner, _ = approved(stores=_stores(buckets, fail=True))
    report = _report(detail)
    assert detail.status == ExperimentStatus.APPROVED
    assert report.status == ReportStatus.FAILED
    with Session(app_engine) as s:
        row = s.get(m.Report, report.id)
        assert row is not None and row.attempts == report_service.MAX_ATTEMPTS
    assert _audit(app_engine, report.id, "report.generation_failed") == 1
    assert owner.get(f"/verify/{report.id}").status_code == 404
    # Sinh lại bằng store bình thường: cùng report_id.
    _, good = _client(api, _stores(buckets), Role.REVIEWER)
    again = _post(good, f"/reports/{report.id}/regenerate")
    assert again.status_code == 200, again.text
    after = ReportView.model_validate(good.get(f"/reports/{report.id}").json()["report"])
    assert (after.id, after.status) == (report.id, ReportStatus.READY)
    assert _post(good, f"/reports/{report.id}/regenerate").status_code == 409


def test_verify_is_public_and_minimal(approved: Any, api: Api) -> None:
    _, detail, _, _ = approved()
    report = _report(detail)
    anonymous = api.env.client()
    response = anonymous.get(f"/verify/{report.id}")
    assert response.status_code == 200
    info = VerifyInfo.model_validate(response.json())
    assert (info.json_sha256, info.pdf_sha256) == (report.json_sha256, report.pdf_sha256)
    assert set(response.json()) == {"report_id", "issued_at", "json_sha256", "pdf_sha256"}
    assert anonymous.get(f"/verify/{uuid.uuid4()}").status_code == 404


def test_no_report_before_approval() -> None:
    """Không endpoint nào sinh report cho experiment chưa approved: chỉ có sinh lại report
    `failed` (report chỉ được tạo trong quyết định approve)."""
    paths = json.loads(OPENAPI.read_text())["paths"]
    writes = {p for p, ops in paths.items() if p.startswith("/reports") and "post" in ops}
    assert writes == {"/reports/{report_id}/regenerate"}


def test_resume_generating(
    approved: Any, buckets: Buckets, app_engine: Engine, owner_engine: Engine
) -> None:
    """Report kẹt ở `generating` (API dừng giữa chừng) được sinh tiếp lúc khởi động."""
    _, detail, _, _ = approved(stores=_stores(buckets, fail=True))
    report = _report(detail)
    with Session(owner_engine) as s, s.begin():
        s.execute(
            update(m.Report)
            .where(m.Report.id == report.id)
            .values(status=ReportStatus.GENERATING, attempts=0)
        )
    count = report_service.resume_generating(sessionmaker(app_engine), _stores(buckets))
    assert count >= 1
    with Session(app_engine) as s:
        row = s.get(m.Report, report.id)
        assert row is not None and row.status == ReportStatus.READY
