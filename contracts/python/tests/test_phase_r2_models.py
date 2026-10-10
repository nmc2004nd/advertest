"""Contract Phase R2 (requirements.md Phase R2, Data / Fields)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from advertest_contracts.enums import SpecCheckName
from advertest_contracts.hashing import sha256_of
from advertest_contracts.models import (
    AttackSpec,
    AttackSpecAdminView,
    AttackSpecBody,
    AttackSpecMetadata,
    ExperimentCreate,
    ExperimentInsight,
    ExperimentPreset,
    ModelCard,
    ModelRegister,
    ModelUploadCreate,
    ProtocolTemplate,
    QuickTryObject,
    QuickTryView,
    SpecCheckResult,
    ToolJobResult,
    Weakness,
    compute_spec_sha256,
)

ROOT = Path(__file__).resolve().parents[2]
MOCKS = ROOT / "mocks"
SEEDS = ROOT / "seeds"


def _mock(schema: str, name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((MOCKS / schema / f"{name}.json").read_text())
    return data


def _seed(name: str) -> list[dict[str, Any]]:
    data: list[dict[str, Any]] = json.loads((SEEDS / name).read_text())
    return data


def _specs() -> dict[str, AttackSpec]:
    return {s["name"]: AttackSpec.model_validate(s) for s in _seed("attack_specs.json")}


# ---------------------------------------------------------------- Attack spec


def test_adapter_none_is_omitted_so_seed_hash_is_unchanged() -> None:
    for spec in _specs().values():
        assert spec.adapter is None
        assert "adapter" not in spec.model_dump(mode="json")
        assert spec.spec_sha256 == compute_spec_sha256(spec)


def test_adapter_changes_hash() -> None:
    fog = _specs()["fog"]
    body = fog.model_dump(mode="json", include=set(AttackSpecBody.model_fields))
    with_adapter = AttackSpecBody.model_validate(body | {"adapter": "corruption.imagecorruptions"})
    assert sha256_of(with_adapter) != fog.spec_sha256


@pytest.mark.parametrize("adapter", ["Corruption.x", "corruption", "a..b", "a.b.", ".a.b", "a-b.c"])
def test_adapter_name_pattern(adapter: str) -> None:
    body = _specs()["fog"].model_dump(mode="json", include=set(AttackSpecBody.model_fields))
    with pytest.raises(ValidationError):
        AttackSpecBody.model_validate(body | {"adapter": adapter})


def test_metadata_level_labels() -> None:
    meta = AttackSpecMetadata.model_validate(_mock("attack_spec_metadata", "fog"))
    assert meta.label_for(3.0) == "vừa"
    assert meta.label_for(2) is None
    base = meta.model_dump(mode="json")
    for labels in ({"x": "a"}, {"1": "a", "1.0": "b"}, {"nan": "a"}, {"1": ""}):
        with pytest.raises(ValidationError):
            AttackSpecMetadata.model_validate(base | {"level_labels": labels})


def test_metadata_is_outside_spec_hash() -> None:
    view = AttackSpecAdminView.model_validate(_mock("attack_spec_admin_view", "snow_light_pending"))
    assert view.metadata is not None
    assert view.spec_sha256 == compute_spec_sha256(view)


def test_admin_view_is_active_matches_status() -> None:
    data = _mock("attack_spec_admin_view", "snow_light_pending")
    with pytest.raises(ValidationError, match="is_active"):
        AttackSpecAdminView.model_validate(data | {"is_active": True})
    AttackSpecAdminView.model_validate(data | {"is_active": True, "status": "active"})


def test_spec_check_result_rules() -> None:
    ok = _mock("spec_check_result", "passed")
    SpecCheckResult.model_validate(ok)
    with pytest.raises(ValidationError):  # thiếu mục mà vẫn passed
        SpecCheckResult.model_validate(ok | {"items": ok["items"][:6]})
    with pytest.raises(ValidationError):  # sai thứ tự
        SpecCheckResult.model_validate(ok | {"items": list(reversed(ok["items"]))})
    with pytest.raises(ValidationError):  # có error mà vẫn passed
        SpecCheckResult.model_validate(ok | {"error": "Quá 120 giây"})
    failed = _mock("spec_check_result", "batch_failed")
    assert not SpecCheckResult.model_validate(failed).passed
    item = failed["items"][4] | {"details": None}
    with pytest.raises(ValidationError, match="details"):
        SpecCheckResult.model_validate(failed | {"items": [*failed["items"][:4], item]})
    assert next(iter(SpecCheckName)) == SpecCheckName.RUNS


# ---------------------------------------------------------------- Model


def test_model_card_onnx_never_supports_gradients() -> None:
    card = _mock("model_card", "yolov8n")
    assert card["supports_gradients"] is True
    with pytest.raises(ValidationError, match="onnx"):
        ModelCard.model_validate(card | {"framework": "onnx"})


@pytest.mark.parametrize("filename", ["m.pt", "m.pkl", "m.zip", "m.onnx.pt", "a/m.onnx", "m"])
def test_upload_rejects_other_extensions(filename: str) -> None:
    with pytest.raises(ValidationError):
        ModelUploadCreate.model_validate({"filename": filename, "size_bytes": 10})


def test_upload_size_limit() -> None:
    ModelUploadCreate.model_validate({"filename": "m.safetensors", "size_bytes": 500 * 2**20})
    with pytest.raises(ValidationError):
        ModelUploadCreate.model_validate({"filename": "m.onnx", "size_bytes": 500 * 2**20 + 1})


def test_register_torchvision_architecture_allowlist() -> None:
    data = _mock("model_register", "torchvision")
    ModelRegister.model_validate(data)
    with pytest.raises(ValidationError, match="architecture"):
        ModelRegister.model_validate(data | {"architecture": "maskrcnn_resnet50_fpn"})
    onnx = _mock("model_register", "onnx")
    ModelRegister.model_validate(onnx | {"architecture": "bất kỳ mô tả nào"})
    with pytest.raises(ValidationError):
        ModelRegister.model_validate(onnx | {"framework": "ultralytics"})
    with pytest.raises(ValidationError):
        ModelRegister.model_validate(onnx | {"class_names": ["car", "car"]})


# ---------------------------------------------------------------- Insight


def test_insight_rules() -> None:
    weak = _mock("experiment_insight", "weak")
    ExperimentInsight.model_validate(weak)
    with pytest.raises(ValidationError):  # quá 5 điểm yếu
        ExperimentInsight.model_validate(weak | {"weaknesses": weak["weaknesses"] * 3})
    with pytest.raises(ValidationError):  # robust nhưng có điểm yếu
        ExperimentInsight.model_validate(
            weak | {"conclusion": weak["conclusion"] | {"code": "robust"}}
        )
    with pytest.raises(ValidationError):  # dải khác 4 dải cố định
        ExperimentInsight.model_validate(weak | {"bands": weak["bands"][:3]})
    row = weak["matrix"][0]
    with pytest.raises(ValidationError):  # thiếu ô
        ExperimentInsight.model_validate(weak | {"matrix": [row | {"cells": row["cells"][:3]}]})
    no_data = _mock("experiment_insight", "no_data")
    with pytest.raises(ValidationError):
        ExperimentInsight.model_validate(
            no_data | {"conclusion": no_data["conclusion"] | {"code": "weak"}}
        )


def test_weakness_kind_fields() -> None:
    grid = _mock("experiment_insight", "weak")["weaknesses"][0]
    Weakness.model_validate(grid)
    with pytest.raises(ValidationError):
        Weakness.model_validate(grid | {"relative_drop": None})
    search = grid | {"kind": "search", "relative_drop": None, "breaking_point": 5.0}
    Weakness.model_validate(search)
    with pytest.raises(ValidationError):
        Weakness.model_validate(search | {"breaking_point": None})
    with pytest.raises(ValidationError):
        Weakness.model_validate(grid | {"class_relative_drop": None})


def test_promoted_from_is_omitted_when_null() -> None:
    clone = _mock("experiment_clone", "promoted_small_slice")
    config = ExperimentCreate.model_validate(clone["config"])
    assert config.promoted_from is not None
    plain = ExperimentCreate.model_validate(clone["config"] | {"promoted_from": None})
    assert "promoted_from" not in plain.model_dump(mode="json")


# ---------------------------------------------------------------- Template và preset


def test_protocol_templates_seed() -> None:
    templates = [ProtocolTemplate.model_validate(t) for t in _seed("protocol_templates.json")]
    assert [t.key for t in templates] == ["quick", "front_camera", "weather", "full"]
    specs = _specs()
    for template in templates:
        for attack in template.attacks:
            spec = specs[attack.attack_spec_name]
            if attack.search is not None:
                assert not spec.requires_training, "patch không ở chế độ tìm ngưỡng"


def test_experiment_presets_seed() -> None:
    presets = [ExperimentPreset.model_validate(p) for p in _seed("experiment_presets.json")]
    assert [p.key for p in presets] == ["fast", "standard", "deep"]
    by_key = {p.key: p for p in presets}
    assert by_key["deep"].use_search and not by_key["standard"].use_search
    # Thử nhanh mặc định preset standard: 5 level (requirements.md Phase R2, Thử nhanh).
    assert len(by_key["standard"].level_ratios) == 5


# ---------------------------------------------------------------- Thử nhanh và job công cụ


def test_quick_try_object_status() -> None:
    obj = {"bbox": [0, 0, 10, 10], "class_name": "car", "clean_score": 0.9, "attacked_score": 0.5}
    QuickTryObject.model_validate(obj | {"status": "kept"})
    with pytest.raises(ValidationError):
        QuickTryObject.model_validate(obj | {"status": "lost"})
    QuickTryObject.model_validate(obj | {"status": "lost", "attacked_score": None})
    QuickTryObject.model_validate(obj | {"status": "new", "clean_score": None})


def test_quick_try_view_rules() -> None:
    done = _mock("quick_try_view", "completed")
    assert QuickTryView.model_validate(done).not_a_test_result is True
    with pytest.raises(ValidationError):
        QuickTryView.model_validate(done | {"not_a_test_result": False})
    with pytest.raises(ValidationError):
        QuickTryView.model_validate(done | {"clean_image_url": None})
    with pytest.raises(ValidationError):  # URL MinIO trực tiếp không được phục vụ
        QuickTryView.model_validate(done | {"clean_image_url": "http://minio:9000/x"})
    queued = _mock("quick_try_view", "queued")
    with pytest.raises(ValidationError):
        QuickTryView.model_validate(queued | {"error": "x"})


def test_tool_job_result_needs_exactly_one() -> None:
    data = _mock("tool_job_result", "error")
    ToolJobResult.model_validate(data)
    with pytest.raises(ValidationError):
        ToolJobResult.model_validate(data | {"error": None})
    report = _mock("tool_job_result", "spec_check")["report"]
    with pytest.raises(ValidationError):
        ToolJobResult.model_validate(data | {"report": report})
