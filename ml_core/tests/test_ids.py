"""Mọi ID sinh từ hash dùng `advertest_contracts.ids.content_id` (plan.md Phase 1 task 6)."""

import re
from pathlib import Path

ML_CORE = Path(__file__).resolve().parents[1]
FORBIDDEN = re.compile(r"\buuid5\b|\bNAMESPACE_(DNS|URL|OID|X500)\b|\bUUID\(\s*[\"']")


def test_no_private_uuid5_namespace_in_ml_core() -> None:
    offenders = [
        f"{path.relative_to(ML_CORE)}:{lineno}"
        for path in ML_CORE.rglob("*.py")
        if path.parent.name != "tests"
        for lineno, line in enumerate(path.read_text().splitlines(), start=1)
        if FORBIDDEN.search(line)
    ]
    assert offenders == [], f"Dùng advertest_contracts.ids.content_id thay vì: {offenders}"
