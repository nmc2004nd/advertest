"""validation.md Phase R2, Group 1 — Template, preset, gợi ý tiêu chí (`test_templates.py`, `db`).

- `GET /protocol-templates` trả 4 template của seed; `draft` là `ProtocolCreate` hợp lệ, dùng spec
  `active`, level suy từ `level_ratios`, tiêu chí gợi ý đúng ngưỡng theo `strictness`; không đổi khi
  DB có thêm kết quả experiment; `POST /protocols` nhận bản nháp.
- `POST /experiments/draft` với từng preset: level đúng công thức, hợp level bắt buộc; `deep` chạy
  tìm ngưỡng thay cho quét lưới với attack không bị bắt buộc quét lưới (trừ patch); kết quả qua
  được `POST /experiments/estimate`; không tạo experiment.

Công thức (requirements.md Phase R2, Chốt ở Group 0): level = round(min + r·(max - min), 6); tham số
rời rạc lấy giá trị gần nhất trong `values` (hòa lấy nhỏ hơn), bỏ trùng; tiêu chí quét lưới ở level
bắt buộc thứ (n - 1) // 2 đã sắp xếp; tìm ngưỡng ở lo + 0.5·(hi - lo).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from advertest_contracts.models import (
    STRICTNESS_MAX_DROP,
    ExperimentClone,
    ExperimentPreset,
    ProtocolCreate,
    ProtocolTemplate,
)
from backend.app.db import models as m

from .conftest import (
    DEV_OPEN,
    P5,
    count_rows,
    create_protocol,
    error,
    max_drop,
    ok,
    post,
    required_grid,
    spec_of,
    unique,
)

pytestmark = pytest.mark.db

SEEDS = Path(__file__).resolve().parents[3] / "contracts" / "seeds"
TEMPLATES = [
    ProtocolTemplate.model_validate(t)
    for t in json.loads((SEEDS / "protocol_templates.json").read_text())
]
PRESETS = [
    ExperimentPreset.model_validate(p)
    for p in json.loads((SEEDS / "experiment_presets.json").read_text())
]


def level_of(name: str, ratio: float) -> float:
    param = spec_of(name).primary_param
    value = param.min + ratio * (param.max - param.min)
    if param.type == "discrete":
        assert param.values is not None
        return min(param.values, key=lambda v: (abs(v - value), v))
    return round(value, 6)


def levels_of(name: str, ratios: list[float]) -> list[float]:
    return sorted({level_of(name, r) for r in ratios})


@pytest.fixture
def clients(api: Any) -> dict[str, Any]:
    _, _, reviewer = api.user("reviewer")
    _, _, engineer = api.user("engineer")
    target = api.target()
    api.profile(target, sec=0.05, batch=5, attacks=["fgsm", "fog", "adv_patch"])
    return {"reviewer": reviewer, "engineer": engineer, "target": target}


# ---------------------------------------------------------------- template


def test_list_templates_matches_seed(clients: dict[str, Any]) -> None:
    for client in (clients["reviewer"], clients["engineer"]):
        response = client.get("/protocol-templates")
        assert response.status_code == 200, response.text
        got = [ProtocolTemplate.model_validate(t) for t in response.json()]
        assert got == TEMPLATES


def _draft(client: TestClient, key: str) -> ProtocolCreate:
    response = client.get(f"/protocol-templates/{key}/draft")
    assert response.status_code == 200, response.text
    return ProtocolCreate.model_validate(response.json())


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda t: t.key)
def test_template_draft(template: ProtocolTemplate, api: Any, clients: dict[str, Any]) -> None:
    reviewer = clients["reviewer"]
    before = count_rows(api.engine, m.Protocol)
    draft = _draft(reviewer, template.key)
    assert count_rows(api.engine, m.Protocol) == before  # bản nháp không tạo protocol
    body = draft.body
    assert body.min_slice_size == template.min_slice_size
    assert [a.attack_spec_name for a in body.required_attacks] == [
        a.attack_spec_name for a in template.attacks
    ]
    threshold = STRICTNESS_MAX_DROP[template.strictness]
    criteria = {c.attack_spec_name: c for c in body.pass_criteria}
    assert set(criteria) == {a.attack_spec_name for a in template.attacks}
    for required, tpl in zip(body.required_attacks, template.attacks, strict=True):
        spec = spec_of(tpl.attack_spec_name)
        assert required.spec_sha256 == spec.spec_sha256  # version đang active
        assert required.mode == tpl.mode
        criterion = criteria[tpl.attack_spec_name]
        if tpl.grid is not None:
            assert required.grid is not None
            levels = levels_of(tpl.attack_spec_name, tpl.grid.level_ratios)
            assert sorted(required.grid.levels) == levels
            assert criterion.kind == "max_drop_at_level"
            assert criterion.level == levels[(len(levels) - 1) // 2]
            assert (criterion.threshold_kind, criterion.threshold) == ("relative_drop", threshold)
            assert criterion.class_filter is None
        else:
            assert tpl.search is not None and required.search is not None
            param = spec.primary_param
            span = param.max - param.min
            lo = round(param.min + tpl.search.lo_ratio * span, 6)
            hi = round(param.min + tpl.search.hi_ratio * span, 6)
            assert (required.search.lo, required.search.hi) == pytest.approx((lo, hi))
            assert required.search.max_tol == pytest.approx(tpl.search.max_tol_ratio * (hi - lo))
            assert criterion.kind == "min_breaking_point"
            assert criterion.level == pytest.approx(lo + 0.5 * (hi - lo))
            assert (criterion.threshold_kind, criterion.threshold) == (
                tpl.search.threshold_kind, tpl.search.threshold,
            )  # fmt: skip

    payload = {"name": unique(template.key), "body": body.model_dump(mode="json")}
    created = post(reviewer, "/protocols", payload)
    assert created.status_code == 201, created.text


def test_template_draft_ignores_experiment_results(api: Any, clients: dict[str, Any]) -> None:
    """Gợi ý chỉ phụ thuộc template và catalog (mission.md nguyên tắc 2)."""
    before = [_draft(clients["reviewer"], t.key) for t in TEMPLATES]
    body = api.body(clients["target"], [P5.attack("fgsm", [2.0, 4.0])])
    experiment_id = ok(post(clients["engineer"], "/experiments", body)).json()["id"]
    api.work(clients["target"], experiment_id)
    assert [_draft(clients["reviewer"], t.key) for t in TEMPLATES] == before


def test_template_draft_permissions_and_unknown(clients: dict[str, Any]) -> None:
    assert error(clients["engineer"].get("/protocol-templates/quick/draft"))[:2] == (
        403, "forbidden",
    )  # fmt: skip
    assert clients["reviewer"].get("/protocol-templates/khong_co/draft").status_code == 404


# ---------------------------------------------------------------- preset


def test_list_presets_matches_seed(clients: dict[str, Any]) -> None:
    response = clients["engineer"].get("/experiment-presets")
    assert response.status_code == 200, response.text
    assert [ExperimentPreset.model_validate(p) for p in response.json()] == PRESETS


def _draft_request(
    api: Any, target: Any, protocol_id: str, preset: str, **kw: Any
) -> dict[str, Any]:
    w = api.world
    body: dict[str, Any] = {
        "protocol_id": protocol_id,
        "preset": preset,
        "model_version_id": w.model_id,
        "slice_id": w.slice_id,
        "class_mapping_id": w.mapping_id,
        "compute_target_id": target.id,
        "limit": {"kind": "time", "value": "7200"},
    }
    body.update(kw)
    return body


def _experiment_draft(client: TestClient, body: dict[str, Any]) -> ExperimentClone:
    response = post(client, "/experiments/draft", body)
    assert response.status_code == 200, response.text
    return ExperimentClone.model_validate(response.json())


@pytest.mark.parametrize("preset", PRESETS, ids=lambda p: p.key)
def test_experiment_draft_dev_protocol(
    preset: ExperimentPreset, api: Any, clients: dict[str, Any]
) -> None:
    engineer, target = clients["engineer"], clients["target"]
    fgsm, fog = spec_of("fgsm"), spec_of("fog")
    before = count_rows(api.engine, m.Experiment)
    body = _draft_request(
        api, target, DEV_OPEN, preset.key, attack_spec_ids=[str(fgsm.id), str(fog.id)]
    )
    clone = _experiment_draft(engineer, body)
    assert count_rows(api.engine, m.Experiment) == before
    attacks = {str(a.attack_spec_id): a for a in clone.config.attacks}
    assert set(attacks) == {str(fgsm.id), str(fog.id)}
    for name, spec in (("fgsm", fgsm), ("fog", fog)):
        attack = attacks[str(spec.id)]
        assert attack.seed == 0 and attack.spec_sha256 == spec.spec_sha256
        if preset.use_search:
            assert preset.search is not None
            assert attack.mode == "search" and attack.search is not None
            param = spec.primary_param
            assert (attack.search.lo, attack.search.hi) == (param.min, param.max)
            assert attack.search.tol == pytest.approx((param.max - param.min) / 256)
            assert attack.search.threshold_kind == preset.search.threshold_kind
            assert attack.search.threshold == preset.search.threshold
            # Tập con không vượt slice (5 ảnh).
            assert attack.search.subset_size == min(preset.search.subset_size, 5)
        else:
            assert attack.mode == "grid" and attack.grid is not None
            assert sorted(attack.grid.levels) == levels_of(name, preset.level_ratios)
    estimate = post(engineer, "/experiments/estimate", clone.config.model_dump(mode="json"))
    assert estimate.status_code == 200, estimate.text


@pytest.mark.parametrize("preset", PRESETS, ids=lambda p: p.key)
def test_experiment_draft_official_protocol(
    preset: ExperimentPreset, api: Any, clients: dict[str, Any]
) -> None:
    protocol = create_protocol(
        clients["reviewer"],
        required_attacks=[required_grid("fgsm", [2.0, 4.0]), required_grid("fog", [1.0])],
        pass_criteria=[max_drop("fgsm", 4.0)],
    )
    body = _draft_request(api, clients["target"], protocol["id"], preset.key)
    clone = _experiment_draft(clients["engineer"], body)
    attacks = {str(a.attack_spec_id): a for a in clone.config.attacks}
    assert set(attacks) == {str(spec_of("fgsm").id), str(spec_of("fog").id)}
    for name, required in (("fgsm", [2.0, 4.0]), ("fog", [1.0])):
        attack = attacks[str(spec_of(name).id)]
        assert attack.mode == "grid" and attack.grid is not None  # bắt buộc quét lưới
        assert sorted(attack.grid.levels) == sorted(
            set(levels_of(name, preset.level_ratios)) | set(required)
        )
    estimate = post(
        clients["engineer"], "/experiments/estimate", clone.config.model_dump(mode="json")
    )
    assert estimate.status_code == 200, estimate.text


def test_experiment_draft_whole_catalog_and_patch(api: Any, clients: dict[str, Any]) -> None:
    """`attack_spec_ids = null` là toàn bộ catalog active trừ spec cần train; chọn rõ patch thì
    cần `training_slice_id` (422 khi thiếu)."""
    engineer, target = clients["engineer"], clients["target"]
    clone = _experiment_draft(engineer, _draft_request(api, target, DEV_OPEN, "standard"))
    names = {spec_of(n).id: n for n in (
        "fgsm", "pgd_linf", "pgd_l2", "fog", "snow", "frost", "motion_blur", "contrast",
        "bbox_occlusion",
    )}  # fmt: skip
    assert {a.attack_spec_id for a in clone.config.attacks} == set(names)

    patch = spec_of("adv_patch")
    body = _draft_request(api, target, DEV_OPEN, "deep", attack_spec_ids=[str(patch.id)])
    assert error(post(engineer, "/experiments/draft", body))[0] == 422
    with_training = _draft_request(
        api, target, DEV_OPEN, "deep", attack_spec_ids=[str(patch.id)],
        training_slice_id=api.world.slice_id,
    )  # fmt: skip
    response = post(engineer, "/experiments/draft", with_training)
    # Slice huấn luyện trùng slice đánh giá: bản nháp vẫn dựng được, estimate báo 422 như Phase 6.
    assert response.status_code == 200, response.text
    (attack,) = ExperimentClone.model_validate(response.json()).config.attacks
    assert attack.mode == "grid"  # deep không áp tìm ngưỡng cho patch
    assert attack.grid is not None
    assert sorted(attack.grid.levels) == levels_of("adv_patch", PRESETS[-1].level_ratios)
    assert str(attack.training_slice_id) == api.world.slice_id
    config = ExperimentClone.model_validate(response.json()).config.model_dump(mode="json")
    assert error(post(engineer, "/experiments/estimate", config))[0] == 422
