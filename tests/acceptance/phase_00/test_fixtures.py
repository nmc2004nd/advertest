"""Nghiệm thu Phase 0, mục Fixture (validation.md).

Test manifest.json và smoke test YOLOv8n viết cùng phần còn lại của Group 6 (cần 5 ảnh KITTI).
"""

from __future__ import annotations

from ml_core.fixtures import FIXTURES_DIR, load_checksums, sha256_file


def test_every_fixture_present_with_matching_sha256() -> None:
    files = load_checksums()
    assert files
    for item in files:
        path = FIXTURES_DIR / item.path
        assert path.is_file(), f"Thiếu {item.path}: chạy `make fixtures`"
        assert sha256_file(path) == item.sha256, item.path
