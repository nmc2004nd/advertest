"""validation.md Phase R3, Group 2 — `validate` kiểm `art_class` (`test_validate_art_class.py`).

- `PerturbationRegistry.validate` báo `InvalidSpec` khi adapter ART nhận `art_class` không có trong
  danh sách lớp builder hỗ trợ; spec seed validate được (không cần DB).
- `POST /admin/attack-specs` với `art_class` lạ → 422 ngay, không tạo spec (marker `db`).
"""

from __future__ import annotations

from typing import Any

import pytest

from advertest_contracts.ids import content_id
from advertest_contracts.models import AttackSpec, AttackSpecBody
from advertest_contracts.models import compute_spec_sha256 as sha
from attacks.builders import DEFAULT_REGISTRY, InvalidSpec
from attacks.registry import load_catalog
from backend.app.db import models as m

from .conftest import count_rows, post, spec_of, unique

UNSUPPORTED = "CarliniL2Method"


def _spec(base_name: str, **changes: Any) -> AttackSpec:
    base = next(s for s in load_catalog() if s.name == base_name)
    body = base.model_dump(mode="json", include=set(AttackSpecBody.model_fields))
    body.update(changes)
    digest = sha(AttackSpecBody.model_validate(body))
    return AttackSpec.model_validate({**body, "id": str(content_id(digest)), "spec_sha256": digest})


@pytest.mark.parametrize("spec", load_catalog(), ids=lambda s: s.name)
def test_seed_specs_validate(spec: AttackSpec) -> None:
    DEFAULT_REGISTRY.validate(spec)


@pytest.mark.parametrize("base", ["fgsm", "pgd_linf"])
def test_unsupported_art_class_rejected(base: str) -> None:
    spec = _spec(base, name=unique("bad_art"), art_class=UNSUPPORTED)
    with pytest.raises(InvalidSpec):
        DEFAULT_REGISTRY.validate(spec)


def test_patch_with_evasion_class_rejected() -> None:
    patch = next(s for s in load_catalog() if s.requires_training)
    spec = _spec(patch.name, name=unique("bad_patch"), art_class="FastGradientMethod",
                 adapter="patch.robust_dpatch")  # fmt: skip
    with pytest.raises(InvalidSpec):
        DEFAULT_REGISTRY.validate(spec)


@pytest.mark.db
def test_create_spec_with_unsupported_art_class_422(api: Any) -> None:
    _, _, admin = api.user("admin")
    body = spec_of("fgsm").model_dump(mode="json", include=set(AttackSpecBody.model_fields))
    body.update(name=unique("bad_art"), version=1, art_class=UNSUPPORTED)
    metadata = {"display_name": "Sai lớp ART", "description": "Spec thử lớp ART chưa hỗ trợ.",
                "realism": "low", "level_labels": {}}  # fmt: skip
    before = count_rows(api.engine, m.AttackSpecRow)
    response = post(admin, "/admin/attack-specs", {"body": body, "metadata": metadata})
    assert response.status_code == 422, response.text
    assert count_rows(api.engine, m.AttackSpecRow) == before
