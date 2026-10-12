"""Nhận xét chi tiết bằng LLM cho trang experiment (không dùng cho thử nhanh, không vào report).

- Dữ liệu gửi LLM (`build_input`) chỉ gồm số liệu: insight, metric của từng level, điểm gãy, tên
  model, slice và class. Không gửi ảnh, URI hay thông tin người dùng.
- Nhận xét lưu theo `input_sha256` (sha256 canonical_json của dữ liệu đó) và `PROMPT_VERSION`:
  cùng dữ liệu thì dùng lại bản đã lưu, không gọi LLM lần nữa (mission.md nguyên tắc 5). Có run
  mới làm dữ liệu đổi thì bản cũ là `stale`, người dùng bấm tạo lại.
- Chỉ tạo khi experiment đã kết thúc và có run có metric (`can_generate`).
- Gọi LLM ngoài transaction DB (có thể mất tới `LLM_TIMEOUT_S`).
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from advertest_contracts.enums import ConclusionCode
from advertest_contracts.hashing import sha256_of
from advertest_contracts.models import (
    MAX_NARRATIVE_ITEMS,
    ExperimentNarrative,
    NarrativeFinding,
    NarrativeState,
    RunMetrics,
)
from backend.app.db import models as m
from backend.app.insight import rules
from backend.app.insight.llm import LlmClient
from backend.app.insight.service import UNFINISHED, InsightAttackData, InsightData, collect
from backend.app.services import audit
from backend.app.services.errors import Conflict, LlmFailed, LlmUnavailable
from backend.app.services.experiment_config import spec_of

PROMPT_VERSION = "1"
TOP_CLASSES = 3

SYSTEM_PROMPT = """\
Bạn là kỹ sư kiểm thử độ bền (robustness) của model phát hiện vật thể cho xe tự hành. Người dùng \
gửi số liệu một experiment adversarial dạng JSON. Hãy viết nhận xét chi tiết bằng tiếng Việt cho \
kỹ sư và người duyệt đọc.

Ý nghĩa số liệu:
- relative_drop: mức sụt tương đối của mAP@0.5 so với ảnh sạch (0.62 nghĩa là giảm 62%).
- level: cường độ attack theo tham số chính (param); level_ratio = level / param.max.
- attack_success_rate: tỉ lệ vật thể detect đúng trên ảnh sạch bị mất sau attack.
- worst_classes: các class sụt AP50 tương đối nhiều nhất tại level đó.
- mode "grid": quét các level; mode "search": tự tìm điểm gãy (breaking_point).
- weaknesses và rule_conclusion: điểm yếu và câu kết luận hệ thống đã tính theo luật.
- experiment.partial = true: kết quả một phần (experiment chưa xong hoặc chạm giới hạn).

Quy tắc:
- Chỉ dựa vào số liệu được gửi; không bịa số. Nêu nhận định kèm số cụ thể (phần trăm làm tròn).
- So sánh các attack với nhau, chỉ ra xu hướng theo level (sụt tăng dần, sụt đột ngột, điểm gãy) \
và class yếu nhất. Nếu kết quả tốt thì nói rõ là tốt.
- Được nêu nguyên nhân khả dĩ nhưng ghi rõ đó là giả thuyết.
- Nếu partial = true thì nói rõ đây là kết quả một phần.
- Không kết luận model an toàn để triển khai thật: đây là môi trường mô phỏng.
- next_steps là gợi ý cho kỹ sư (xem failure case nào, thêm level hay attack nào, hướng cải \
thiện); con người quyết định.
- Giữ nguyên tên attack, tên class, các thuật ngữ mAP, AP50, level.

Trả về đúng một object JSON, không thêm chữ nào ngoài JSON:
{"summary": "2-3 câu tóm tắt", "findings": [{"title": "tiêu đề ngắn", "detail": "2-4 câu"}], \
"next_steps": ["một gợi ý"]}
findings có 2-5 mục, next_steps có 1-5 mục."""


def _num(value: float | None) -> float | None:
    return None if value is None else round(value, 4)


def _worst_classes(metrics: RunMetrics) -> list[dict[str, Any]]:
    drops = sorted(
        (
            (-(value.clean_ap50 - value.attacked_ap50) / value.clean_ap50, name, value)
            for name, value in (metrics.per_class or {}).items()
            if value.clean_ap50 and value.attacked_ap50 is not None
        ),
        key=lambda item: (item[0], item[1]),
    )
    return [
        {
            "class": name,
            "clean_ap50": _num(value.clean_ap50),
            "attacked_ap50": _num(value.attacked_ap50),
            "relative_drop": _num(-negative_drop),
        }
        for negative_drop, name, value in drops[:TOP_CLASSES]
    ]


def _attack_input(attack: InsightAttackData) -> dict[str, Any]:
    spec = spec_of(attack.row)
    param = spec.primary_param
    meta = attack.target.metadata
    item: dict[str, Any] = {
        "name": attack.row.name,
        "display_name": meta.display_name if meta else None,
        "kind": str(attack.row.kind),
        "param": {"name": param.name, "unit": param.unit, "min": param.min, "max": param.max},
    }
    if attack.grid is None:
        item["mode"] = "search"
        item["breaking_point"] = _num(attack.breaking_point)
        return item
    item["mode"] = "grid"
    item["levels"] = [
        {
            "level": _num(run.level),
            "level_ratio": _num(rules.level_ratio(run.level, param.max)),
            "label": rules._label(attack.target, run.level),
            "clean_map50": _num(run.metrics.clean.map50),
            "attacked_map50": _num(run.metrics.attacked.map50),
            "relative_drop": _num(run.metrics.relative_drop),
            "attack_success_rate": _num(run.metrics.attack_success_rate),
            "partial": run.metrics.partial,
            "worst_classes": _worst_classes(run.metrics),
        }
        for run in sorted(attack.grid, key=lambda run: run.level)
    ]
    return item


def build_input(session: Session, data: InsightData) -> dict[str, Any]:
    """Dữ liệu gửi LLM; chỉ số liệu, thứ tự ổn định để hash không đổi khi dữ liệu không đổi."""
    experiment = data.experiment
    version = session.get(m.ModelVersion, experiment.model_version_id)
    assert version is not None  # khóa ngoại không null
    model = session.get(m.Model, version.model_id)
    assert model is not None
    slice_row = session.get(m.Slice, experiment.slice_id)
    assert slice_row is not None
    insight = data.insight
    return {
        "experiment": {
            "name": experiment.name,
            "mode": str(insight.mode),
            "partial": insight.partial,
        },
        "model": {
            "name": model.name,
            "framework": version.framework,
            "input_size": version.input_size,
            "num_classes": len(version.class_names),
        },
        "slice": {"name": slice_row.name, "num_images": len(slice_row.image_ids)},
        "rule_conclusion": insight.conclusion.text,
        "weaknesses": [
            weakness.model_dump(mode="json", exclude={"attack_spec_id"})
            for weakness in insight.weaknesses
        ],
        "attacks": [_attack_input(attack) for attack in data.attacks],
    }


def _can_generate(data: InsightData) -> bool:
    return (
        data.experiment.status not in UNFINISHED
        and data.insight.conclusion.code != ConclusionCode.NO_DATA
    )


def _view(row: m.ExperimentNarrativeRow) -> ExperimentNarrative:
    return ExperimentNarrative.model_validate(
        {
            **row.content,
            "experiment_id": row.experiment_id,
            "input_sha256": row.input_sha256,
            "prompt_version": row.prompt_version,
            "llm_model": row.llm_model,
            "partial": row.partial,
            "created_by": row.created_by,
            "created_at": row.created_at,
        }
    )


def _rows(session: Session, experiment_id: UUID) -> list[m.ExperimentNarrativeRow]:
    """Các bản đã lưu, mới nhất trước."""
    return list(
        session.scalars(
            select(m.ExperimentNarrativeRow)
            .where(m.ExperimentNarrativeRow.experiment_id == experiment_id)
            .order_by(m.ExperimentNarrativeRow.created_at.desc())
        )
    )


def _matching(rows: list[m.ExperimentNarrativeRow], digest: str) -> m.ExperimentNarrativeRow | None:
    return next(
        (r for r in rows if r.input_sha256 == digest and r.prompt_version == PROMPT_VERSION),
        None,
    )


def state(session: Session, experiment_id: UUID, *, enabled: bool) -> NarrativeState:
    data = collect(session, experiment_id)
    digest = sha256_of(build_input(session, data))
    rows = _rows(session, experiment_id)
    current = _matching(rows, digest)
    shown = current or (rows[0] if rows else None)
    return NarrativeState(
        enabled=enabled,
        narrative=_view(shown) if shown else None,
        stale=shown is not None and current is None,
        can_generate=_can_generate(data),
    )


def _clip(text: Any, limit: int) -> str:
    value = str(text).strip() if text is not None else ""
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def parse_content(raw: dict[str, Any]) -> dict[str, Any]:
    """Nội dung LLM trả → `summary`, `findings`, `next_steps` hợp lệ theo contract (cắt bớt mục
    hoặc chữ quá dài); thiếu `summary` hoặc sai kiểu thì `LlmFailed`."""
    try:
        findings = [
            NarrativeFinding(title=_clip(f["title"], 200), detail=_clip(f["detail"], 2000))
            for f in raw.get("findings") or []
            if isinstance(f, dict) and f.get("title") and f.get("detail")
        ][:MAX_NARRATIVE_ITEMS]
        steps = [_clip(s, 500) for s in raw.get("next_steps") or [] if str(s).strip()]
        summary = _clip(raw.get("summary"), 2000)
        if not summary:
            raise LlmFailed("LLM trả nội dung không đúng định dạng. Vui lòng thử lại.")
        return {
            "summary": summary,
            "findings": [f.model_dump() for f in findings],
            "next_steps": steps[:MAX_NARRATIVE_ITEMS],
        }
    except (ValidationError, TypeError, AttributeError) as exc:
        raise LlmFailed("LLM trả nội dung không đúng định dạng. Vui lòng thử lại.") from exc


def generate(
    factory: sessionmaker[Session],
    experiment_id: UUID,
    *,
    user_id: UUID,
    client: LlmClient | None,
) -> ExperimentNarrative:
    """Bản nhận xét cho dữ liệu hiện tại: dùng lại bản đã lưu nếu có, ngược lại gọi LLM rồi lưu
    (409 khi experiment chưa kết thúc hoặc chưa có dữ liệu, 503 khi chưa cấu hình LLM)."""
    if client is None:
        raise LlmUnavailable("Máy chủ chưa cấu hình LLM cho nhận xét chi tiết")
    with factory.begin() as session:
        data = collect(session, experiment_id)
        if not _can_generate(data):
            raise Conflict("Chỉ tạo nhận xét khi experiment đã kết thúc và có run có metric")
        payload = build_input(session, data)
        digest = sha256_of(payload)
        existing = _matching(_rows(session, experiment_id), digest)
        if existing is not None:
            return _view(existing)
        partial = data.insight.partial

    raw = client.chat_json(
        SYSTEM_PROMPT,
        "Số liệu experiment (JSON):\n" + json.dumps(payload, ensure_ascii=False, indent=1),
    )
    content = parse_content(raw)

    with factory.begin() as session:
        inserted = session.execute(
            insert(m.ExperimentNarrativeRow)
            .values(
                experiment_id=experiment_id,
                input_sha256=digest,
                prompt_version=PROMPT_VERSION,
                llm_model=client.model,
                content=content,
                partial=partial,
                created_by=user_id,
            )
            .on_conflict_do_nothing(
                index_elements=["experiment_id", "input_sha256", "prompt_version"]
            )
            .returning(m.ExperimentNarrativeRow.id)
        ).scalar_one_or_none()
        if inserted is not None:
            audit.record(
                session,
                actor=session.get(m.User, user_id),
                action="experiment.narrative",
                entity_type="experiment",
                entity_id=experiment_id,
                after={
                    "input_sha256": digest,
                    "prompt_version": PROMPT_VERSION,
                    "llm_model": client.model,
                },
            )
        row = _matching(_rows(session, experiment_id), digest)
        assert row is not None  # vừa thêm, hoặc request song song đã thêm
        return _view(row)
