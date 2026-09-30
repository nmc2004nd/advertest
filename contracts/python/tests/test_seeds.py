import json
from pathlib import Path

from advertest_contracts.ids import content_id
from advertest_contracts.models import AttackSpec, compute_spec_sha256

SEEDS = Path(__file__).resolve().parents[2] / "seeds" / "attack_specs.json"


def _load() -> list[AttackSpec]:
    return [AttackSpec.model_validate(item) for item in json.loads(SEEDS.read_text())]


def test_seed_specs_validate_and_hash_matches() -> None:
    for spec in _load():
        assert spec.spec_sha256 == compute_spec_sha256(spec)
        assert spec.id == content_id(spec.spec_sha256)


def test_seed_catalog_contents() -> None:
    specs = {spec.name: spec for spec in _load()}
    # Phase 0 seed attack của Phase 2; Phase 6 thêm corruption, occlusion và patch.
    corruptions = {"fog", "snow", "frost", "motion_blur", "contrast"}
    white_box = {"fgsm", "pgd_linf", "pgd_l2", "adv_patch"}
    assert set(specs) == white_box | corruptions | {"bbox_occlusion"}
    assert specs["pgd_linf"].fixed_params["max_iter"] == 10
    assert specs["pgd_linf"].fixed_params["eps_step_ratio"] == 0.25
    assert specs["pgd_l2"].primary_param.max == 16
    for name in white_box:
        assert specs[name].requires_gradients and specs[name].access == "white_box"
    for name in corruptions | {"bbox_occlusion"}:
        spec = specs[name]
        assert spec.access == "not_applicable" and not spec.requires_gradients
        assert not spec.requires_training and spec.art_class is None
    for name in corruptions:
        param = specs[name].primary_param
        assert (param.name, param.type, param.values) == ("severity", "discrete", [1, 2, 3, 4, 5])
    occlusion = specs["bbox_occlusion"].primary_param
    assert (occlusion.name, occlusion.min, occlusion.max) == ("occlusion_ratio", 0, 0.9)
    patch = specs["adv_patch"]
    assert patch.art_class == "RobustDPatch" and patch.requires_training
    assert patch.training is not None and patch.training.max_iter == 200
    assert patch.training.max_training_images == 50 and patch.training.checkpoint_every == 50
    assert (patch.primary_param.name, patch.primary_param.min, patch.primary_param.max) == (
        "area_ratio",
        0.02,
        0.25,
    )
