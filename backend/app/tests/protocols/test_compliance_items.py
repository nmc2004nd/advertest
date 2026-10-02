"""Mục tuân thủ theo attack (Phase 8 task 9), không cần DB."""

from __future__ import annotations

from typing import Any

import pytest

from advertest_contracts.enums import ComplianceCode
from advertest_contracts.models import AttackConfig, AttackSpec, RequiredAttack
from attacks.registry import get_spec, load_catalog
from backend.app.protocols.compliance import _attack_items

C = ComplianceCode


def _spec(name: str) -> AttackSpec:
    return get_spec(load_catalog(), name=name)


def _required(name: str, mode: str = "grid", **extra: Any) -> RequiredAttack:
    spec = _spec(name)
    body: dict[str, Any] = {
        "attack_spec_name": name, "spec_sha256": spec.spec_sha256, "mode": mode,
    }  # fmt: skip
    if mode == "grid":
        body["grid"] = {"levels": extra.get("levels", [2, 4])}
    else:
        body["search"] = {
            "threshold_kind": "relative_drop", "threshold": 0.2, "lo": 0, "hi": 32,
            "max_tol": 0.25, "min_bootstrap_samples": 200, **extra,
        }  # fmt: skip
    return RequiredAttack.model_validate(body)


def _config(name: str, mode: str = "grid", **extra: Any) -> tuple[AttackConfig, AttackSpec]:
    spec = _spec(name)
    body: dict[str, Any] = {
        "attack_spec_id": str(spec.id), "spec_sha256": spec.spec_sha256, "mode": mode, "seed": 0,
    }  # fmt: skip
    if mode == "grid":
        body["grid"] = {"levels": extra.pop("levels", [2, 4, 8])}
    else:
        body["search"] = {
            "threshold_kind": "relative_drop", "threshold": 0.2, "lo": 0, "hi": 32,
            "tol": 0.125, "bootstrap_samples": 200, **extra,
        }  # fmt: skip
    return AttackConfig.model_validate(body), spec


def _codes(items: list[Any]) -> dict[ComplianceCode, bool]:
    return {item.code: item.satisfied for item in items}


def test_missing_attack() -> None:
    items = _attack_items(_required("fgsm"), None)
    assert _codes(items) == {C.ATTACK_PRESENT: False}
    assert items[0].attack_spec_name == "fgsm"


def test_grid_ok_with_extra_levels() -> None:
    codes = _codes(_attack_items(_required("fgsm"), _config("fgsm")))
    assert codes == {C.ATTACK_PRESENT: True, C.SPEC_SHA256: True, C.MODE: True,
                     C.GRID_LEVELS: True}  # fmt: skip


def test_grid_missing_level() -> None:
    items = _attack_items(_required("fgsm", levels=[2, 16]), _config("fgsm"))
    assert _codes(items)[C.GRID_LEVELS] is False
    assert "16" in next(i.detail for i in items if i.code == C.GRID_LEVELS)


def test_wrong_spec_version() -> None:
    attack, spec = _config("fgsm")
    attack = attack.model_copy(update={"spec_sha256": "0" * 64})
    assert _codes(_attack_items(_required("fgsm"), (attack, spec)))[C.SPEC_SHA256] is False


def test_wrong_mode_skips_details() -> None:
    codes = _codes(_attack_items(_required("pgd_linf", "search"), _config("pgd_linf")))
    assert codes == {C.ATTACK_PRESENT: True, C.SPEC_SHA256: True, C.MODE: False}


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"threshold": 0.3}, C.SEARCH_THRESHOLD),
        ({"threshold_kind": "absolute_drop"}, C.SEARCH_THRESHOLD),
        ({"class_filter": "person"}, C.SEARCH_THRESHOLD),
        ({"lo": 1}, C.SEARCH_RANGE),
        ({"hi": 16}, C.SEARCH_RANGE),
        ({"tol": 0.5}, C.SEARCH_TOL),
        ({"bootstrap_samples": 100}, C.SEARCH_BOOTSTRAP),
        ({"bootstrap_samples": 0}, C.SEARCH_BOOTSTRAP),
    ],
)
def test_search_rules(change: dict[str, Any], code: ComplianceCode) -> None:
    codes = _codes(
        _attack_items(_required("pgd_linf", "search"), _config("pgd_linf", "search", **change))
    )
    assert codes[code] is False
    assert all(ok for other, ok in codes.items() if other != code)


def test_search_wider_range_and_finer_tol_are_ok() -> None:
    items = _attack_items(
        _required("pgd_linf", "search", lo=1, hi=16),
        _config("pgd_linf", "search", lo=0, hi=32, tol=0.01, bootstrap_samples=500),
    )
    assert all(item.satisfied for item in items)


def test_zero_bootstrap_allowed_when_protocol_allows() -> None:
    items = _attack_items(
        _required("pgd_linf", "search", min_bootstrap_samples=0),
        _config("pgd_linf", "search", bootstrap_samples=0),
    )
    assert all(item.satisfied for item in items)
