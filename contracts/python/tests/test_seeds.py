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
    # Phase 0 chỉ seed attack của Phase 2; patch, corruption, occlusion được thêm ở Phase 6.
    assert set(specs) == {"fgsm", "pgd_linf", "pgd_l2"}
    assert specs["pgd_linf"].fixed_params["max_iter"] == 10
    assert specs["pgd_linf"].fixed_params["eps_step_ratio"] == 0.25
    assert specs["pgd_l2"].primary_param.max == 16
    assert all(spec.requires_gradients for spec in specs.values())
