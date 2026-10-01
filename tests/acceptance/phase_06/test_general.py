"""validation.md Phase 6, Chung: 7 spec mới hợp lệ; hash của dữ liệu cũ không đổi sau khi thêm
trường Phase 6; roadmap đã chuyển làm mờ sang Phase 6.

Mốc so sánh là dữ liệu ở cuối Phase 5 (commit `99c81ff`, trước Group 0 của Phase 6): hash của 3
spec cũ, mock manifest và experiment chép vào `data/`.
"""

from __future__ import annotations

import json
from pathlib import Path

from advertest_contracts.hashing import compute_fingerprint, sha256_of
from advertest_contracts.ids import content_id
from advertest_contracts.models import (
    AttackSpec,
    ExperimentConfig,
    FingerprintInputs,
    Manifest,
    compute_spec_sha256,
)

REPO = Path(__file__).resolve().parents[3]
DATA = Path(__file__).resolve().parent / "data"
SEEDS = REPO / "contracts" / "seeds" / "attack_specs.json"
PHASE05_SPECS = {
    "fgsm": "a6d81b6643af13e1d2f7983ce51340f54c26629304f1fdd98b954c236c1e735f",
    "pgd_linf": "68fe8f72f176fe27981eadfe8b5e98bb36b8e85fc41c97b5702e2e149f52d72c",
    "pgd_l2": "fb54ce834934be1340423f2fb4283b37766e2c1ca74a8fceea9b762e64f7351e",
}
NEW_SPECS = {"fog", "snow", "frost", "motion_blur", "contrast", "bbox_occlusion", "adv_patch"}


def _seeds() -> dict[str, AttackSpec]:
    specs = [AttackSpec.model_validate(item) for item in json.loads(SEEDS.read_text())]
    return {spec.name: spec for spec in specs}


def test_seven_new_specs_validate_with_matching_hash() -> None:
    specs = _seeds()
    assert set(specs) == set(PHASE05_SPECS) | NEW_SPECS
    for name in NEW_SPECS:
        spec = specs[name]
        assert spec.spec_sha256 == compute_spec_sha256(spec), name
        assert spec.id == content_id(spec.spec_sha256), name


def test_old_spec_hashes_unchanged() -> None:
    specs = _seeds()
    assert {name: specs[name].spec_sha256 for name in PHASE05_SPECS} == PHASE05_SPECS


def test_old_manifest_fingerprint_unchanged() -> None:
    data = json.loads((DATA / "phase05_manifest.json").read_text())
    inputs = FingerprintInputs.model_validate(data["fingerprint_inputs"])
    assert inputs.patch_key is None
    assert compute_fingerprint(inputs) == data["fingerprint"]
    assert Manifest.model_validate(data).fingerprint == data["fingerprint"]


def test_old_experiment_config_sha256_unchanged() -> None:
    data = json.loads((DATA / "phase05_experiment_detail.json").read_text())
    config = ExperimentConfig.model_validate(data["config"])
    assert all(a.training_slice_id is None for a in config.attacks)
    assert sha256_of(config) == data["config_sha256"]


def test_roadmap_moves_anonymization_to_phase_06() -> None:
    roadmap = (REPO / "specs" / "roadmap.md").read_text()
    phase6 = roadmap[roadmap.index("## Phase 6") : roadmap.index("## Phase 7")]
    phase10 = roadmap[roadmap.index("## Phase 10") :]
    assert "làm mờ" in phase6.lower().split("\n")[0]
    assert "Làm mờ mặt và biển số" in phase6
    assert "chuyển sang Phase 6" in phase10
