import json
from pathlib import Path

import pytest

from advertest_contracts.models import compute_spec_sha256
from attacks.registry import SEED_FILE, UnknownAttack, get_spec, load_catalog


def test_catalog_has_phase_2_attacks() -> None:
    catalog = load_catalog()
    assert {spec.name for spec in catalog} >= {"fgsm", "pgd_linf", "pgd_l2"}


def test_lookup_by_name_and_hash() -> None:
    catalog = load_catalog()
    pgd = get_spec(catalog, name="pgd_linf")
    assert pgd.art_class == "ProjectedGradientDescent"
    assert get_spec(catalog, spec_sha256=pgd.spec_sha256) == pgd


def test_lookup_by_name_returns_latest_version(tmp_path: Path) -> None:
    items = json.loads(SEED_FILE.read_text())
    fgsm = next(item for item in items if item["name"] == "fgsm")
    v2 = {**fgsm, "version": 2}
    v2["spec_sha256"] = compute_spec_sha256(v2)
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps([v2, fgsm]))
    catalog = load_catalog(path)
    assert get_spec(catalog, name="fgsm").version == 2
    assert get_spec(catalog, spec_sha256=fgsm["spec_sha256"]).version == 1


def test_unknown_and_bad_arguments() -> None:
    catalog = load_catalog()
    with pytest.raises(UnknownAttack, match="patch"):
        get_spec(catalog, name="patch")
    with pytest.raises(UnknownAttack):
        get_spec(catalog, spec_sha256="0" * 64)
    with pytest.raises(ValueError):
        get_spec(catalog)
    with pytest.raises(ValueError):
        get_spec(catalog, name="fgsm", spec_sha256="0" * 64)
