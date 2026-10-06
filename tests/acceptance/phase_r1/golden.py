"""Golden của Phase R1: chụp kết quả lớp chạy trước khi refactor rồi so lại sau mỗi bước
(`tech-stack.md` mục 9, luật 8).

Provenance được ghim: `GIT_COMMIT` cố định, không có `DOCKER_IMAGE_DIGEST`; `lib_versions` đi theo
lockfile nên được ghi vào golden và so riêng (lockfile đổi thì ghi lại golden có chủ đích).

Torch chạy 1 luồng intra-op và `use_deterministic_algorithms` (`pinned_threads`): PGD trên CPU
nhiều luồng không tất định giữa các process ở mức failure case (thứ tự cộng dồn; đo 2026-10-06:
4 luồng, cùng cấu hình, hai process cho FP mới 24 và 25), và `YOLO.predict` của Ultralytics tự đổi
số luồng. Metric vẫn trong sai số ở mọi trường hợp; 1 luồng cho kết quả giống hệt qua 3 process.

So sánh:
- tập run (khóa `<attack>@<level>`, thêm `#<scope>/<order>` với run của tìm ngưỡng) giống hệt;
- `status`, mã lý do, `fingerprint_inputs` (canonical JSON) và `fingerprint` giống từng byte;
- metric trong sai số (`MAP_TOL`, `ASR_TOL`, như Phase 2);
- failure case: cùng thứ tự `image_id`, cùng số object mất và FP mới; severity trong `SEVERITY_TOL`.

Ghi golden: đặt `ADVERTEST_RECORD_GOLDEN=1`; test ghi file rồi fail có chủ đích (chạy lại không có
biến đó để xác nhận). Chỉ người duyệt ghi golden, và chỉ trên code chưa refactor hoặc khi lockfile
đổi.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import torch

from advertest_contracts.hashing import canonical_json, compute_fingerprint
from ml_core.fixtures import FIXTURES_DIR
from ml_core.models.register import lib_versions

GOLDEN_DIR = FIXTURES_DIR / "golden"
RECORD_ENV = "ADVERTEST_RECORD_GOLDEN"
COMMIT = "1" * 40  # khác "0" * 40 của Phase 2: không trùng cache của phase khác trong cùng store

MAP_TOL = 0.005
ASR_TOL = 0.01
SEVERITY_TOL = 0.01
THREADS = 1

# Mỗi spec trong catalog 2 level khác "không biến đổi" (patch chỉ chạy qua worker).
LEVELS: dict[str, list[float]] = {
    "fgsm": [4, 8],
    "pgd_linf": [4, 8],
    "pgd_l2": [1, 2],
    "fog": [1, 3],
    "snow": [1, 3],
    "frost": [1, 3],
    "motion_blur": [1, 3],
    "contrast": [1, 3],
    "bbox_occlusion": [0.3, 0.6],
}
PATCH_LEVELS = [0.05, 0.1]


@pytest.fixture
def pinned_threads() -> Iterator[None]:
    """Torch 1 luồng, thuật toán tất định trong lúc chụp golden; trả lại cấu hình cũ sau đó."""
    threads, deterministic = torch.get_num_threads(), torch.are_deterministic_algorithms_enabled()
    torch.set_num_threads(THREADS)
    torch.use_deterministic_algorithms(True)
    yield
    torch.use_deterministic_algorithms(deterministic)
    torch.set_num_threads(threads)


def run_key(name: str, level: float, scope: str = "full", order: int | None = None) -> str:
    key = f"{name}@{level!r}"
    if order is not None:
        key += f"#{scope}/{order}"
    return key


def case_entry(record: dict[str, Any], rank: int) -> dict[str, Any]:
    """`rank`: thứ tự trong `RunResult.failure_case_ids` (CLI) hoặc cột `rank` (DB)."""
    return {
        "image_id": record["image_id"],
        "rank": rank,
        "severity_score": record["severity_score"],
        "lost_objects": record["lost_objects"],
        "new_false_positives": record["new_false_positives"],
    }


def run_entry(
    *,
    status: str,
    reason: str | None,
    fingerprint: str | None,
    fingerprint_inputs: dict[str, Any] | None,
    metrics: dict[str, Any] | None,
    cases: list[dict[str, Any]],
) -> dict[str, Any]:
    if fingerprint_inputs is not None:
        assert compute_fingerprint(fingerprint_inputs) == fingerprint, "fingerprint lệch inputs"
    return {
        "status": status,
        "reason": reason,
        "fingerprint": fingerprint,
        "fingerprint_inputs": fingerprint_inputs,
        "metrics": metrics,
        "cases": sorted(cases, key=lambda c: c["rank"]),
    }


def snapshot(runs: dict[str, dict[str, Any]], **extra: Any) -> dict[str, Any]:
    return {
        "schema": 1,
        "pinned": {"git_commit": COMMIT, "docker_image_digest": "none"},
        "lib_versions": lib_versions().model_dump(mode="json"),
        "runs": dict(sorted(runs.items())),
        **extra,
    }


# ---------------------------------------------------------------- so sánh


def _close(path: str, actual: Any, expected: Any, errors: list[str]) -> None:
    """So từng lá: số thực theo sai số chọn theo tên trường, còn lại bằng tuyệt đối."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        if set(actual) != set(expected):
            errors.append(f"{path}: khóa {sorted(actual)} != {sorted(expected)}")
            return
        for key in expected:
            _close(f"{path}.{key}", actual[key], expected[key], errors)
    elif isinstance(expected, list) and isinstance(actual, list):
        if len(actual) != len(expected):
            errors.append(f"{path}: độ dài {len(actual)} != {len(expected)}")
            return
        for i, (a, e) in enumerate(zip(actual, expected, strict=True)):
            _close(f"{path}[{i}]", a, e, errors)
    elif isinstance(expected, float) and isinstance(actual, (int, float)):
        leaf = path.rsplit(".", 1)[-1]
        tol = ASR_TOL if "success_rate" in leaf else SEVERITY_TOL if "severity" in leaf else MAP_TOL
        if abs(actual - expected) > tol:
            errors.append(f"{path}: {actual} lệch {expected} quá {tol}")
    elif actual != expected:
        errors.append(f"{path}: {actual!r} != {expected!r}")


def _exact(path: str, actual: Any, expected: Any, errors: list[str]) -> None:
    if canonical_json(actual) != canonical_json(expected):
        errors.append(f"{path}: khác golden\n  thực tế: {actual}\n  golden:  {expected}")


def compare(actual: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if actual["lib_versions"] != expected["lib_versions"]:
        return [
            "lib_versions khác golden (lockfile đã đổi): ghi lại golden có chủ đích "
            f"({RECORD_ENV}=1).\n  thực tế: {actual['lib_versions']}\n"
            f"  golden:  {expected['lib_versions']}"
        ]
    got, want = actual["runs"], expected["runs"]
    if set(got) != set(want):
        missing, unexpected = sorted(set(want) - set(got)), sorted(set(got) - set(want))
        errors.append(f"tập run khác: thiếu {missing}, thừa {unexpected}")
    for key in sorted(set(got) & set(want)):
        a, e = got[key], want[key]
        for field in ("status", "reason", "fingerprint"):
            if a[field] != e[field]:
                errors.append(f"{key}.{field}: {a[field]!r} != {e[field]!r}")
        inputs = "fingerprint_inputs"
        _exact(f"{key}.{inputs}", a[inputs], e[inputs], errors)
        _close(f"{key}.metrics", a["metrics"], e["metrics"], errors)
        _close(f"{key}.cases", a["cases"], e["cases"], errors)
    extra = {k: v for k, v in expected.items() if k not in {"runs", "lib_versions"}}
    for name, value in extra.items():
        _close(name, actual.get(name), value, errors)
    return errors


def check_or_record(actual: dict[str, Any], path: Path) -> None:
    """So `actual` với golden ở `path`; với `ADVERTEST_RECORD_GOLDEN=1` thì ghi rồi fail."""
    if os.environ.get(RECORD_ENV) == "1":
        path.write_text(json.dumps(actual, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
        pytest.fail(f"Đã ghi golden {path.name}; chạy lại không có {RECORD_ENV} để xác nhận")
    assert path.is_file(), f"Chưa có golden {path.name}: người duyệt ghi bằng {RECORD_ENV}=1"
    errors = compare(actual, json.loads(path.read_text()))
    assert not errors, "Lệch golden:\n" + "\n".join(errors)
