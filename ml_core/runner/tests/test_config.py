from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from attacks.registry import get_spec, load_catalog
from ml_core.runner.config import (
    LocalRunConfig,
    experiment_id,
    load_config,
    resolve_specs,
)

IDS = {
    "model_id": "81686f0e-32b6-5806-819c-3b0e37072342",
    "slice_id": "37341deb-7761-5c9b-adf1-e84a9d3f53a8",
    "mapping_id": "820ed6c7-5af9-599b-ac06-905c59f826d6",
}


def _attack(name: str, levels: list[float], seed: int = 0) -> dict[str, Any]:
    spec = get_spec(load_catalog(), name=name)
    return {
        "attack_spec_id": str(spec.id),
        "spec_sha256": spec.spec_sha256,
        "mode": "grid",
        "grid": {"levels": levels},
        "seed": seed,
    }


def _config(**overrides: Any) -> dict[str, Any]:
    return {**IDS, "attacks": [_attack("pgd_linf", [2, 4])], **overrides}


def test_load_config_defaults(tmp_path: Path) -> None:
    path = tmp_path / "run.yaml"
    path.write_text(yaml.safe_dump(_config()))
    config = load_config(path)
    assert config.batch_size == 8 and config.failure_cases_per_run == 20 and config.device is None
    assert [s.name for s in resolve_specs(config)] == ["pgd_linf"]


def test_rejects_search_mode_unknown_fields_and_bad_values(tmp_path: Path) -> None:
    search = {
        **_attack("pgd_linf", [1]),
        "mode": "search",
        "grid": None,
        "search": {
            "threshold_kind": "relative_drop",
            "threshold": 0.2,
            "lo": 0,
            "hi": 16,
            "tol": 1,
            "coarse_n": 4,
            "subset_size": 100,
        },
    }
    with pytest.raises(ValidationError, match="grid"):
        LocalRunConfig.model_validate(_config(attacks=[search]))
    with pytest.raises(ValidationError):
        LocalRunConfig.model_validate(_config(extra=1))
    with pytest.raises(ValidationError):
        LocalRunConfig.model_validate(_config(batch_size=0))
    with pytest.raises(ValidationError):
        LocalRunConfig.model_validate(_config(attacks=[]))
    path = tmp_path / "list.yaml"
    path.write_text("- 1\n")
    with pytest.raises(ValueError, match="mapping"):
        load_config(path)


def test_resolve_specs_checks_id() -> None:
    wrong = {**_attack("fgsm", [4]), "attack_spec_id": _attack("pgd_l2", [1])["attack_spec_id"]}
    with pytest.raises(ValueError, match="không khớp"):
        resolve_specs(LocalRunConfig.model_validate(_config(attacks=[wrong])))


def test_experiment_id_depends_on_whole_config() -> None:
    a = LocalRunConfig.model_validate(_config())
    assert experiment_id(a) == experiment_id(LocalRunConfig.model_validate(_config()))
    assert experiment_id(a) != experiment_id(LocalRunConfig.model_validate(_config(batch_size=4)))


def test_example_config_is_valid() -> None:
    path = Path(__file__).resolve().parents[3] / "configs" / "examples" / "pgd_sweep.yaml"
    config = load_config(path)
    assert [s.name for s in resolve_specs(config)] == ["pgd_linf", "fgsm"]
    assert [a.grid.levels for a in config.attacks if a.grid] == [[2, 4, 8, 16], [4, 8]]
