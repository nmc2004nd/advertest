"""Render report HTML → PDF (Phase 8 task 20, 21), không cần DB: dùng mock snapshot."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from pypdf import PdfReader

from advertest_contracts.models import ReportGridAttack, ReportSnapshot
from backend.app.reports import render

MOCKS = Path(__file__).resolve().parents[4] / "contracts" / "mocks" / "report_snapshot"
PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
    b"\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00\xc9\xfe\x92\xef"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture(scope="module", params=["approved_grid", "search_dirty"])
def snapshot(request: pytest.FixtureRequest) -> ReportSnapshot:
    return ReportSnapshot.model_validate_json((MOCKS / f"{request.param}.json").read_text())


def test_html_has_nine_sections_and_notes(snapshot: ReportSnapshot) -> None:
    html = render.html(snapshot, lambda key: PNG)
    for number in range(1, 10):
        assert f"<h2>{number}. " in html
    for note in snapshot.notes:
        assert note.text.split(";")[0] in html.replace("&#39;", "'")
    assert "BẢN CHÍNH THỨC" in html


def test_pdf_footer_on_every_page(snapshot: ReportSnapshot) -> None:
    pdf = PdfReader(io.BytesIO(render.pdf(render.html(snapshot, lambda key: PNG))))
    for page in pdf.pages:
        text = " ".join((page.extract_text() or "").split()).replace(" ", "")
        assert "BẢNCHÍNHTHỨC" in text
        assert str(snapshot.report_id) in text
        assert f"/verify/{snapshot.report_id}" in text


def test_html_escapes_user_text(snapshot: ReportSnapshot) -> None:
    hostile = snapshot.model_copy(
        update={
            "summary": snapshot.summary.model_copy(
                update={"conclusion": "<script>alert(1)</script>"}
            )
        }
    )
    html = render.html(hostile, lambda key: PNG)
    assert "<script>" not in html and "&lt;script&gt;" in html


def test_grid_chart_needs_points() -> None:
    empty = ReportGridAttack.model_validate(
        {"attack_spec_id": "8d15422d-f111-5c7e-96eb-e704767e6218", "attack_spec_name": "fgsm",
         "points": []}
    )  # fmt: skip
    assert render.grid_chart(empty) is None
