"""validation.md Phase 7, Tập con (`test_subset.py`).

`data/phase05_manifest.json` (chép từ mốc của Phase 6) và `data/phase06_patch_manifest.json` (mock
`manifest/patch_run.json` ở commit ngay trước kickoff Phase 7, `ff11ffd^`) là manifest mốc: Phase 7
thêm `eval_image_ids_sha256` vào fingerprint mà không được đổi fingerprint của run cũ.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from uuid import uuid4

from advertest_contracts.hashing import compute_fingerprint
from advertest_contracts.models import FingerprintInputs, Manifest
from ml_core.search.subset import eval_image_ids_sha256, select_subset

DATA = Path(__file__).parent / "data"
IMAGES = [f"{i:06d}" for i in range(300)]


def test_same_seed_same_subset_regardless_of_input_order() -> None:
    first = select_subset(IMAGES, seed=42, size=100)
    shuffled = IMAGES[:]
    random.Random(7).shuffle(shuffled)
    assert select_subset(shuffled, seed=42, size=100) == first
    assert len(set(first)) == 100 and set(first) <= set(IMAGES)
    other = select_subset(IMAGES, seed=43, size=100)
    assert set(other) != set(first)
    # Slice không lớn hơn kích thước tập con: cả slice.
    assert set(select_subset(IMAGES[:50], seed=42, size=100)) == set(IMAGES[:50])


def _inputs(base: dict[str, object], **changes: object) -> FingerprintInputs:
    return FingerprintInputs.model_validate({**base, **changes})


def test_subset_run_fingerprint_differs_from_full_slice_run() -> None:
    base = json.loads((DATA / "phase05_manifest.json").read_text())["fingerprint_inputs"]
    subset = select_subset(IMAGES, seed=0, size=100)
    subset_sha = eval_image_ids_sha256(subset)
    full_sha = eval_image_ids_sha256(IMAGES)
    assert subset_sha != full_sha
    assert (
        eval_image_ids_sha256(list(reversed(subset))) == subset_sha
    )  # theo tập, không theo thứ tự
    on_subset = _inputs(base, eval_image_ids_sha256=subset_sha)
    on_full = _inputs(base)
    assert compute_fingerprint(on_subset) != compute_fingerprint(on_full)
    # Hai tập con khác nhau (khác seed) cũng khác fingerprint.
    other = _inputs(
        base, eval_image_ids_sha256=eval_image_ids_sha256(select_subset(IMAGES, 1, 100))
    )
    assert compute_fingerprint(other) != compute_fingerprint(on_subset)


def test_full_slice_run_omits_field_and_old_fingerprints_unchanged() -> None:
    for name in ("phase05_manifest.json", "phase06_patch_manifest.json"):
        data = json.loads((DATA / name).read_text())
        assert "eval_image_ids_sha256" not in data["fingerprint_inputs"], name
        inputs = FingerprintInputs.model_validate(data["fingerprint_inputs"])
        assert inputs.eval_image_ids_sha256 is None
        dumped = json.loads(inputs.model_dump_json())
        assert "eval_image_ids_sha256" not in dumped, name
        assert dumped == data["fingerprint_inputs"], name
        assert compute_fingerprint(inputs) == data["fingerprint"], name
        assert (
            Manifest.model_validate({**data, "run_id": str(uuid4())}).fingerprint
            == data["fingerprint"]
        )
