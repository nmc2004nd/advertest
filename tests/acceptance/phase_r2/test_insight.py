"""validation.md Phase R2, Group 1 — Insight (`test_insight.py`, marker `db`).

- Experiment fixture chạy bằng worker thật: `weaknesses` đúng luật và đúng thứ tự, tối đa 5; ma trận
  đủ 4 dải, ô trống là `null`; `partial` đúng khi có run `stopped_limit` hoặc experiment chưa xong.
- Bảng đầu vào → `Conclusion.code` (`no_data`, `robust`, `weak`, `weak_class`); cùng đầu vào cho
  cùng `text` (hàm thuần `backend.app.insight.phrases.conclude`, Chốt ở Group 0).
- `mode`: experiment gắn protocol `dev` là `exploration`, protocol khác là `official`; lọc `?mode=`.

Giá trị kỳ vọng của điểm yếu và ma trận được tính lại trong test từ metric của từng run (`GET
/experiments/{id}/runs`) theo luật ở requirements.md Phase R2, Behaviour Insight.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from advertest_contracts.enums import ConclusionCode
from advertest_contracts.models import (
    MAX_WEAKNESSES,
    ROBUSTNESS_BANDS,
    WEAKNESS_DROP,
    WEAKNESS_VISIBLE_DROP,
    ExperimentInsight,
    Weakness,
)

from .conftest import P5, create_protocol, max_drop, ok, post, required_grid

pytestmark = pytest.mark.db

ATTACKS: dict[str, list[float]] = {
    "fgsm": [1.0, 2.0, 4.0],
    "fog": [1.0, 3.0, 5.0],
    "contrast": [1.0, 5.0],
    "bbox_occlusion": [0.45, 0.9],
}


def _insight(client: TestClient, experiment_id: str) -> ExperimentInsight:
    response = client.get(f"/experiments/{experiment_id}/insight")
    assert response.status_code == 200, response.text
    return ExperimentInsight.model_validate(response.json())


def _runs(client: TestClient, experiment_id: str) -> list[dict[str, Any]]:
    response = client.get(f"/experiments/{experiment_id}/runs")
    assert response.status_code == 200, response.text
    runs: list[dict[str, Any]] = response.json()
    return runs


def _class_drop(metrics: dict[str, Any]) -> dict[str, float]:
    drops = {}
    for name, value in (metrics.get("per_class") or {}).items():
        clean, attacked = value["clean_ap50"], value["attacked_ap50"]
        if clean and attacked is not None:
            drops[name] = (clean - attacked) / clean
    return drops


def _expected(runs: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, list[Any]]]:
    """Điểm yếu (grid) và ma trận theo luật của requirements.md, từ run có metric."""
    by_attack: dict[str, list[dict[str, Any]]] = {}
    for run in runs:
        metrics = run["metrics"]
        if run["status"] not in ("completed", "stopped_limit") or not metrics:
            continue
        if metrics["relative_drop"] is None:
            continue
        by_attack.setdefault(run["attack_spec_id"], []).append(run)
    weaknesses = []
    matrix: dict[str, list[Any]] = {}
    for spec_id, items in by_attack.items():
        items.sort(key=lambda r: r["level"])
        param_max = items[0]["attack_spec"]["param_max"]
        cells: list[Any] = [None] * len(ROBUSTNESS_BANDS)
        for run in items:
            ratio = run["level"] / param_max
            band = next(i for i, (lo, hi) in enumerate(ROBUSTNESS_BANDS) if lo < ratio <= hi)
            drop = run["metrics"]["relative_drop"]
            cells[band] = drop if cells[band] is None else max(cells[band], drop)
        matrix[spec_id] = cells
        hits = [r for r in items if r["metrics"]["relative_drop"] >= WEAKNESS_DROP]
        chosen = hits[0] if hits else max(items, key=lambda r: r["metrics"]["relative_drop"])
        drop = chosen["metrics"]["relative_drop"]
        if drop < WEAKNESS_VISIBLE_DROP:
            continue
        class_drops = _class_drop(chosen["metrics"])
        top = max(class_drops.values(), default=None)
        weaknesses.append(
            {
                "attack_spec_id": spec_id,
                "level": chosen["level"],
                "level_ratio": chosen["level"] / param_max,
                "relative_drop": drop,
                "classes": {k for k, v in class_drops.items() if v == top},
            }
        )
    weaknesses.sort(key=lambda w: (w["level_ratio"], -w["relative_drop"]))
    return weaknesses[:MAX_WEAKNESSES], matrix


@pytest.fixture
def engineer(api: Any) -> tuple[TestClient, Any]:
    _, _, client = api.user("engineer")
    target = api.target()
    api.profile(target, sec=0.05, batch=5, attacks=list(ATTACKS))
    return client, target


def _create(
    api: Any, client: TestClient, target: Any, attacks: dict[str, list[float]], **kw: Any
) -> str:
    body = api.body(target, [P5.attack(n, levels) for n, levels in attacks.items()], **kw)
    experiment_id: str = ok(post(client, "/experiments", body)).json()["id"]
    return experiment_id


def test_weaknesses_and_matrix_follow_rules(api: Any, engineer: tuple[TestClient, Any]) -> None:
    client, target = engineer
    experiment_id = _create(api, client, target, ATTACKS)
    api.work(target, experiment_id)
    insight = _insight(client, experiment_id)
    runs = _runs(client, experiment_id)
    want, matrix = _expected(runs)

    assert insight.partial is False
    assert insight.mode == "exploration"
    assert [list(b) for b in insight.bands] == [list(b) for b in ROBUSTNESS_BANDS]
    assert len(insight.weaknesses) <= MAX_WEAKNESSES
    assert [str(w.attack_spec_id) for w in insight.weaknesses] == [
        w["attack_spec_id"] for w in want
    ]
    for got, exp in zip(insight.weaknesses, want, strict=True):
        assert got.kind == "grid"
        assert got.level == exp["level"]
        assert got.level_ratio == pytest.approx(exp["level_ratio"])
        assert got.relative_drop == pytest.approx(exp["relative_drop"])
        if exp["classes"]:
            assert got.class_name in exp["classes"]
    # FGSM gãy ở eps 2 (mức sụt 0.34 ≥ 0.3, conftest Phase 7): điểm yếu đầu tiên.
    first = insight.weaknesses[0]
    assert first.attack_name == "fgsm" and first.level == 2.0

    rows = {str(r.attack_spec_id): r for r in insight.matrix}
    assert set(rows) == set(matrix)
    for spec_id, cells in matrix.items():
        got_cells = rows[spec_id].cells
        assert [c.band for c in got_cells] == [0, 1, 2, 3]
        for cell, expected in zip(got_cells, cells, strict=True):
            if expected is None:
                assert cell.max_relative_drop is None and cell.runs == 0
            else:
                assert cell.max_relative_drop == pytest.approx(expected)
                assert cell.runs > 0

    again = _insight(client, experiment_id)
    assert again.conclusion == insight.conclusion
    assert insight.conclusion.code in (ConclusionCode.WEAK, ConclusionCode.WEAK_CLASS)
    assert "fgsm" in insight.conclusion.text


def test_partial_when_unfinished_or_stopped_limit(
    api: Any, engineer: tuple[TestClient, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, target = engineer
    queued = _create(api, client, target, {"fgsm": [2.0]})
    insight = _insight(client, queued)
    assert insight.partial is True
    assert insight.conclusion.code == ConclusionCode.NO_DATA
    assert insight.weaknesses == [] and insight.matrix == []
    api.work(target, queued)
    assert _insight(client, queued).partial is False

    # Mỗi lần báo tiến độ tính như 100 giây, giới hạn 350 giây: một phần run `stopped_limit`
    # (như test Phase 8).
    original = P5.WorkerClient.progress

    def slow(self: Any, run_id: UUID, body: Any) -> Any:
        return original(self, run_id, body.model_copy(update={"processing_seconds_delta": 100.0}))

    monkeypatch.setattr(P5.WorkerClient, "progress", slow)
    stopped = _create(
        api, client, target, {"fgsm": [2.0, 4.0, 8.0, 16.0, 32.0]},
        limit={"kind": "time", "value": "350"},
    )  # fmt: skip
    api.work(target, stopped)
    runs = _runs(client, stopped)
    assert any(r["status"] == "stopped_limit" for r in runs)
    assert _insight(client, stopped).partial is True


def test_insight_unknown_experiment_is_404(api: Any, engineer: tuple[TestClient, Any]) -> None:
    client, _ = engineer
    assert client.get(f"/experiments/{uuid4()}/insight").status_code == 404


# ---------------------------------------------------------------- câu kết luận (hàm thuần)


def conclude(weaknesses: list[Weakness], *, has_data: bool) -> Any:
    from backend.app.insight.phrases import conclude as build  # Group 1

    return build(weaknesses, has_data=has_data)


def _weakness(**changes: Any) -> Weakness:
    base: dict[str, Any] = {
        "attack_spec_id": str(uuid4()),
        "attack_name": "fgsm",
        "kind": "grid",
        "level": 4.0,
        "level_ratio": 0.125,
        "level_label": None,
        "relative_drop": 0.42,
        "breaking_point": None,
        "class_name": "car",
        "class_relative_drop": 0.6,
    }
    base.update(changes)
    return Weakness.model_validate(base)


@pytest.mark.parametrize(
    ("weaknesses", "has_data", "code"),
    [
        ([], False, ConclusionCode.NO_DATA),
        ([], True, ConclusionCode.ROBUST),
        ([_weakness()], True, ConclusionCode.WEAK),
        ([_weakness(class_relative_drop=0.84)], True, ConclusionCode.WEAK_CLASS),  # đúng 2 lần
        ([_weakness(relative_drop=0.2, class_relative_drop=0.39)], True, ConclusionCode.WEAK),
        ([_weakness(class_name=None, class_relative_drop=None)], True, ConclusionCode.WEAK),
        (
            [
                _weakness(
                    kind="search",
                    relative_drop=None,
                    breaking_point=3.0,
                    class_name=None,
                    class_relative_drop=None,
                )
            ],
            True,
            ConclusionCode.WEAK,
        ),
    ],
)
def test_conclusion_code_table(weaknesses: list[Weakness], has_data: bool, code: str) -> None:
    conclusion = conclude(weaknesses, has_data=has_data)
    assert conclusion.code == code
    assert conclusion.text.strip()
    assert conclude(weaknesses, has_data=has_data) == conclusion


def test_conclusion_text_names_attack_label_and_drop() -> None:
    weak = _weakness(attack_name="fog", level=3.0, level_ratio=0.6, level_label="sương dày")
    text = conclude([weak], has_data=True).text
    assert "fog" in text and "sương dày" in text and "42" in text
    other = conclude([_weakness(relative_drop=0.55, class_relative_drop=0.6)], has_data=True).text
    assert other != conclude([_weakness()], has_data=True).text


# ---------------------------------------------------------------- mode


def test_mode_follows_protocol_and_filter(api: Any, engineer: tuple[TestClient, Any]) -> None:
    client, target = engineer
    _, _, reviewer = api.user("reviewer")
    protocol = create_protocol(
        reviewer,
        required_attacks=[required_grid("fgsm", [2.0])],
        pass_criteria=[max_drop("fgsm", 2.0)],
    )
    exploration = _create(api, client, target, {"fgsm": [2.0]})
    official = _create(api, client, target, {"fgsm": [2.0]}, protocol_id=protocol["id"])
    modes = {
        e["id"]: e["mode"]
        for e in client.get("/experiments", params={"owner": "me"}).json()["items"]
    }
    assert modes[exploration] == "exploration"
    assert modes[official] == "official"
    assert client.get(f"/experiments/{official}").json()["mode"] == "official"
    for mode, expected in (("exploration", exploration), ("official", official)):
        page = client.get("/experiments", params={"owner": "me", "mode": mode})
        assert page.status_code == 200, page.text
        ids = {e["id"] for e in page.json()["items"]}
        assert expected in ids
        assert all(e["mode"] == mode for e in page.json()["items"])
