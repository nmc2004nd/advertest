"""Nghiệm thu Phase 2, mục Failure case (validation.md)."""

from __future__ import annotations

import io

import numpy as np
from PIL import Image

from advertest_contracts.hashing import sha256_of
from advertest_contracts.ids import content_id
from advertest_contracts.models import FailureCaseRecord, RunResult
from ml_core.data.loader import Batch
from ml_core.store import LocalStore

from .conftest import FAILURE_CASES, Pipeline, Rerun, Sweep


def _records(store: LocalStore, result: RunResult) -> list[FailureCaseRecord]:
    """Record của run theo đúng thứ tự `failure_case_ids`."""
    assert result.manifest_uri is not None
    prefix = result.manifest_uri.rsplit("/", 1)[0]
    by_id = {}
    for key in store.list(f"{prefix}/cases/"):
        if key.endswith("/record.json") and key.count("/") == prefix.count("/") + 3:
            record = FailureCaseRecord.model_validate_json(store.get(key))
            by_id[record.id] = record
    assert set(by_id) == set(result.failure_case_ids)
    return [by_id[i] for i in result.failure_case_ids]


def test_case_count_and_positive_severity(pipeline: Pipeline, sweep: Sweep) -> None:
    some_cases = False
    for result in sweep.results.values():
        records = _records(pipeline.store, result)
        assert len(records) <= FAILURE_CASES
        assert all(r.severity_score > 0 for r in records)
        scores = [(-r.severity_score, r.image_id) for r in records]
        assert scores == sorted(scores), "điểm giảm dần, cùng điểm thì image_id nhỏ trước"
        some_cases = some_cases or bool(records)
    assert some_cases
    assert len(sweep.results[("pgd_linf", 16.0)].failure_case_ids) == FAILURE_CASES


def test_level_zero_has_no_failure_case(sweep: Sweep) -> None:
    for name in ("fgsm", "pgd_linf", "pgd_l2"):
        assert sweep.results[(name, 0.0)].failure_case_ids == []


def test_case_order_is_deterministic(pipeline: Pipeline, sweep: Sweep, forced: Rerun) -> None:
    for key, again in forced.results.items():
        first = [r.image_id for r in _records(pipeline.store, sweep.results[key])]
        second = [r.image_id for r in _records(pipeline.store, again)]
        assert first == second, key


def test_case_files_and_record(pipeline: Pipeline, sweep: Sweep, batch: Batch) -> None:
    store = pipeline.store
    result = sweep.results[("pgd_linf", 8.0)]
    infos = dict(zip(batch.image_ids, batch.infos, strict=True))
    records = _records(store, result)
    assert records
    for record in records:
        assert record.run_id == result.run_id and record.fingerprint == result.fingerprint
        FailureCaseRecord.model_validate_json(record.model_dump_json())
        arrays = {}
        for name in ("clean_png", "adversarial_png", "perturbation_png"):
            key = getattr(record.artifacts, name)
            image = Image.open(io.BytesIO(store.get(key)))
            assert image.format == "PNG" and image.size == (640, 640)
            arrays[name] = np.asarray(image.convert("RGB"))
        # Ảnh nhiễu khuếch đại: vùng pad là 0.5 (128), vùng ảnh thật có nhiễu.
        info = infos[record.image_id]
        left, top = info.pad
        pad_rows = slice(0, top) if top > 0 else slice(640 - left, 640)
        assert np.all(arrays["perturbation_png"][pad_rows] == 128)
        assert np.array_equal(arrays["adversarial_png"][pad_rows], arrays["clean_png"][pad_rows])
        assert np.any(arrays["perturbation_png"] != 128)


def test_case_id_is_uuid5_of_fingerprint_run_and_image(pipeline: Pipeline, sweep: Sweep) -> None:
    # Phase 3 (requirements.md Decisions): id gồm run_id.
    result = sweep.results[("pgd_linf", 16.0)]
    for record in _records(pipeline.store, result):
        assert record.run_id == result.run_id
        expected = content_id(
            sha256_of(
                {
                    "fingerprint": result.fingerprint,
                    "run_id": str(result.run_id),
                    "image_id": record.image_id,
                }
            )
        )
        assert record.id == expected and record.id.version == 5
