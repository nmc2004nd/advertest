"""validation.md Phase R3, Group 1 — Insight trong report (`test_report_insight.py`).

- Report xuất sau R3: `snapshot.insight` bằng insight của experiment lúc xuất; PDF có section
  "Điểm yếu chính" (marker `db`).
- Report xuất trước R3 (snapshot không có `insight`): đọc lại và ghi ra `canonical_json` không đổi
  byte nào (nên `json_sha256` và `/verify` giữ nguyên); HTML của PDF không có section mới.

Interface: `backend.app.reports.render.html(snapshot, read_artifact) -> str` (đã có từ Phase 8).
"""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from typing import Any

import pytest
from PIL import Image
from pypdf import PdfReader

from advertest_contracts.hashing import canonical_json
from advertest_contracts.models import ExperimentInsight, ReportDetail, ReportSnapshot
from backend.app.reports import render

from .conftest import Flow, detail, ok

MOCKS = Path(__file__).resolve().parents[3] / "contracts" / "mocks" / "report_snapshot"
SECTION = "Điểm yếu chính"
DISCLAIMER = "Điểm yếu là gợi ý để review, không thay cho tiêu chí đạt của protocol"


def _png(_key: str) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), (90, 90, 90)).save(buffer, format="PNG")
    return buffer.getvalue()


def _mock(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((MOCKS / f"{name}.json").read_text())
    return data


# ---------------------------------------------------------------- không cần DB


def test_old_snapshot_hash_unchanged() -> None:
    raw = _mock("approved_grid")
    assert "insight" not in raw
    snapshot = ReportSnapshot.model_validate(raw)
    assert snapshot.insight is None
    assert canonical_json(snapshot.model_dump(mode="json")) == canonical_json(raw)


def test_html_without_insight_has_no_section() -> None:
    document = render.html(ReportSnapshot.model_validate(_mock("approved_grid")), _png)
    assert SECTION not in document


def test_html_with_insight_has_section() -> None:
    snapshot = ReportSnapshot.model_validate(_mock("approved_grid_insight"))
    assert snapshot.insight is not None
    document = render.html(snapshot, _png)
    assert SECTION in document
    assert snapshot.insight.conclusion.text in document
    assert DISCLAIMER in document
    for weakness in snapshot.insight.weaknesses:
        assert weakness.attack_name in document
    # Section đứng ngay sau phần tóm tắt, trước phần cấu hình.
    assert document.index("Tóm tắt") < document.index(SECTION) < document.index("Cấu hình")


# ---------------------------------------------------------------- DB, report thật


def _report(flow: Flow, experiment_id: str) -> ReportDetail:
    report = detail(flow.owner, experiment_id).report
    assert report is not None
    response = flow.reviewer.get(f"/reports/{report.id}")
    assert response.status_code == 200, response.text
    return ReportDetail.model_validate(response.json())


@pytest.mark.db
def test_new_report_has_insight(flow: Flow) -> None:
    experiment_id = flow.approved()
    insight = ExperimentInsight.model_validate(
        ok(flow.owner.get(f"/experiments/{experiment_id}/insight")).json()
    )
    report = _report(flow, experiment_id)
    assert report.snapshot is not None and report.snapshot.insight is not None
    stored = report.snapshot.insight
    assert stored.weaknesses == insight.weaknesses
    assert stored.matrix == insight.matrix
    assert stored.bands == insight.bands
    assert stored.conclusion == insight.conclusion

    issued = ok(flow.reviewer.get(f"/reports/{report.report.id}/download?format=json")).json()
    raw = flow.reviewer.get(issued["url"]).content
    assert hashlib.sha256(raw).hexdigest() == report.report.json_sha256
    assert json.loads(raw)["insight"]["conclusion"]["text"] == insight.conclusion.text

    issued = ok(flow.reviewer.get(f"/reports/{report.report.id}/download?format=pdf")).json()
    pdf = flow.reviewer.get(issued["url"]).content
    text = "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages)
    assert SECTION in text
