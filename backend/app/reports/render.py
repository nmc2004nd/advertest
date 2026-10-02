"""Render report: HTML (Jinja2) → PDF (WeasyPrint); biểu đồ matplotlib thành PNG nhúng vào
(requirements.md Phase 8, Sinh report; plan task 20, 21)."""

from __future__ import annotations

import base64
import io
from collections.abc import Callable
from pathlib import Path
from uuid import UUID

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from matplotlib.figure import Figure  # API hướng đối tượng: không cần backend màn hình
from weasyprint import HTML

from advertest_contracts.enums import (
    CaseSeverity,
    CaseVerdictKind,
    CriterionKind,
    CriterionStatus,
    ModelVerdict,
)
from advertest_contracts.models import PassCriterion, ReportGridAttack, ReportSnapshot

Reader = Callable[[str], bytes]
TEMPLATES = Path(__file__).parent / "templates"
_ENV = Environment(
    loader=FileSystemLoader(TEMPLATES),
    autoescape=select_autoescape(["html", "j2"]),
    undefined=StrictUndefined,
)

VERDICT_TEXT = {
    ModelVerdict.MEETS_CRITERIA: "Model đạt tiêu chí",
    ModelVerdict.DOES_NOT_MEET: "Model không đạt tiêu chí",
    ModelVerdict.CONDITIONAL: "Model đạt có điều kiện",
}
STATUS_TEXT = {
    CriterionStatus.PASS: "Đạt",
    CriterionStatus.FAIL: "Không đạt",
    CriterionStatus.INCONCLUSIVE: "Chưa kết luận",
}
STATUS_CLASS = {
    CriterionStatus.PASS: "good",
    CriterionStatus.FAIL: "bad",
    CriterionStatus.INCONCLUSIVE: "warn",
}
SEVERITY_TEXT = {
    CaseSeverity.CRITICAL: "nghiêm trọng",
    CaseSeverity.MAJOR: "lớn",
    CaseSeverity.MINOR: "nhỏ",
    CaseSeverity.ACCEPTABLE: "chấp nhận được",
}
KIND_TEXT = {
    CaseVerdictKind.SAFETY_RELEVANT: "ảnh hưởng an toàn",
    CaseVerdictKind.ACCEPTABLE: "chấp nhận được",
    CaseVerdictKind.ANNOTATION_ISSUE: "lỗi nhãn",
}
TIMELINE_TEXT = {
    "experiment.submitted": "Gửi duyệt",
    "review.claimed": "Nhận review",
    "review.released": "Trả lại review",
    "review.decided": "Quyết định",
}


def criterion_text(criterion: PassCriterion) -> str:
    target = f" (class {criterion.class_filter})" if criterion.class_filter else ""
    if criterion.kind == CriterionKind.MAX_DROP_AT_LEVEL:
        return (
            f"{criterion.attack_spec_name}: {criterion.threshold_kind.value}{target} tại level"
            f" {criterion.level:g} ≤ {criterion.threshold:g}"
        )
    return (
        f"{criterion.attack_spec_name}: điểm gãy ({criterion.threshold_kind.value}"
        f" {criterion.threshold:g}{target}) ≥ {criterion.level:g}"
    )


def _data_uri(data: bytes, media_type: str) -> str:
    return f"data:{media_type};base64,{base64.b64encode(data).decode()}"


def grid_chart(attack: ReportGridAttack) -> str | None:
    """Đường cong mức sụt tương đối theo level (PNG, data URI); None khi không có điểm nào."""
    points = [(p.level, p.relative_drop) for p in attack.points if p.relative_drop is not None]
    if not points:
        return None
    fig = Figure(figsize=(6.4, 2.6), dpi=150)
    ax = fig.subplots()
    ax.plot([lv for lv, _ in points], [d for _, d in points], marker="o", color="#1f5fa8")
    ax.set_xlabel("level")
    ax.set_ylabel("mức sụt tương đối")
    ax.set_ylim(min(0.0, *(d for _, d in points)), max(1.0, *(d for _, d in points)))
    ax.grid(alpha=0.3)
    ax.set_title(attack.attack_spec_name)
    fig.tight_layout()
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png")
    return _data_uri(buffer.getvalue(), "image/png")


def html(snapshot: ReportSnapshot, read_artifact: Reader) -> str:
    """HTML của report. `read_artifact` đọc thumbnail đã làm mờ trong bucket artifacts."""
    thumbs: dict[UUID, str | None] = {}
    for case in snapshot.reviewed_cases:
        thumbs[case.failure_case_id] = _data_uri(read_artifact(case.thumbnail_key), "image/png")
    charts = {g.attack_spec_id: grid_chart(g) for g in snapshot.results.grid}
    spec_names = {a.id: a.name for a in snapshot.configuration.attack_specs}
    return _ENV.get_template("report.html.j2").render(
        s=snapshot,
        verify_path=f"/verify/{snapshot.report_id}",
        charts=charts,
        thumbs=thumbs,
        spec_names=spec_names,
        criterion_text=criterion_text,
        verdict_text=VERDICT_TEXT,
        status_text=STATUS_TEXT,
        status_class=STATUS_CLASS,
        severity_text=SEVERITY_TEXT,
        kind_text=KIND_TEXT,
        timeline_text=TIMELINE_TEXT,
    )


def pdf(document: str) -> bytes:
    result: bytes = HTML(string=document).write_pdf()
    return result
