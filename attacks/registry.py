"""Attack catalog: đọc seed trong `contracts/seeds/` và tra spec theo tên hoặc hash."""

from __future__ import annotations

import json
from pathlib import Path

from advertest_contracts.models import AttackSpec

SEED_FILE = Path(__file__).resolve().parents[1] / "contracts" / "seeds" / "attack_specs.json"


class UnknownAttack(LookupError):
    """Không có spec nào khớp trong catalog."""


def load_catalog(path: Path = SEED_FILE) -> list[AttackSpec]:
    """Mọi spec trong catalog; mỗi spec được validate (gồm `spec_sha256`)."""
    return [AttackSpec.model_validate(item) for item in json.loads(path.read_text())]


def get_spec(
    catalog: list[AttackSpec], *, name: str | None = None, spec_sha256: str | None = None
) -> AttackSpec:
    """Tra đúng một trong `name` (trả version cao nhất) hoặc `spec_sha256` (khớp chính xác)."""
    if (name is None) == (spec_sha256 is None):
        raise ValueError("Cần đúng một trong name hoặc spec_sha256")
    if spec_sha256 is not None:
        for spec in catalog:
            if spec.spec_sha256 == spec_sha256:
                return spec
        raise UnknownAttack(f"Không có attack spec với spec_sha256 = {spec_sha256}")
    matches = [spec for spec in catalog if spec.name == name]
    if not matches:
        known = ", ".join(sorted({spec.name for spec in catalog}))
        raise UnknownAttack(f"Không có attack spec tên {name!r} (có: {known})")
    return max(matches, key=lambda spec: spec.version)
