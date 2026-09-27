"""Tải fixture: chỉ đặt file khi sha256 khớp, bỏ qua file đã đúng, báo lỗi gộp."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from ml_core.fixtures import FixtureError, FixtureFile, fetch_all, fetch_one, load_checksums


def _write_checksums(path: Path, files: list[dict[str, str]], base_url: str = "") -> Path:
    path.write_text(json.dumps({"base_url": base_url, "files": files}))
    return path


@pytest.fixture
def source(tmp_path: Path) -> Path:
    src = tmp_path / "source"
    (src / "kitti" / "image_2").mkdir(parents=True)
    (src / "kitti" / "image_2" / "000001.png").write_bytes(b"png-bytes")
    (src / "weights.pt").write_bytes(b"weights")
    return src


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_fetch_all_downloads_and_verifies(tmp_path: Path, source: Path) -> None:
    checksums = _write_checksums(
        tmp_path / "checksums.json",
        [
            {"path": "kitti/image_2/000001.png", "sha256": _sha(b"png-bytes")},
            {
                "path": "yolov8n.pt",
                "url": (source / "weights.pt").as_uri(),
                "sha256": _sha(b"weights"),
            },
        ],
        base_url=source.as_uri() + "/",
    )
    root = tmp_path / "fixtures"
    assert sorted(fetch_all(checksums, root)) == ["kitti/image_2/000001.png", "yolov8n.pt"]
    assert (root / "kitti/image_2/000001.png").read_bytes() == b"png-bytes"
    # Lần hai: file đã đúng checksum thì không tải lại.
    assert fetch_all(checksums, root) == []


def test_wrong_checksum_leaves_no_file(tmp_path: Path, source: Path) -> None:
    item = FixtureFile(path="weights.pt", sha256="0" * 64, url=(source / "weights.pt").as_uri())
    root = tmp_path / "fixtures"
    with pytest.raises(FixtureError, match="sha256 không khớp"):
        fetch_one(item, root)
    assert list(root.iterdir()) == []


def test_corrupted_existing_file_is_replaced(tmp_path: Path, source: Path) -> None:
    root = tmp_path / "fixtures"
    root.mkdir()
    (root / "weights.pt").write_bytes(b"corrupted")
    item = FixtureFile(
        path="weights.pt", sha256=_sha(b"weights"), url=(source / "weights.pt").as_uri()
    )
    assert fetch_one(item, root) is True
    assert (root / "weights.pt").read_bytes() == b"weights"


def test_errors_are_collected(tmp_path: Path, source: Path) -> None:
    checksums = _write_checksums(
        tmp_path / "checksums.json",
        [
            {"path": "missing.png", "url": (source / "nope.png").as_uri(), "sha256": "0" * 64},
            {"path": "yolov8n.pt", "url": (source / "weights.pt").as_uri(), "sha256": "1" * 64},
        ],
    )
    with pytest.raises(FixtureError) as exc:
        fetch_all(checksums, tmp_path / "fixtures")
    assert "missing.png" in str(exc.value)
    assert "yolov8n.pt" in str(exc.value)


@pytest.mark.parametrize("bad", ["../escape.png", "/etc/passwd"])
def test_paths_must_stay_inside_fixtures(tmp_path: Path, bad: str) -> None:
    checksums = _write_checksums(
        tmp_path / "c.json", [{"path": bad, "url": "file:///x", "sha256": "0" * 64}]
    )
    with pytest.raises(FixtureError, match="phải nằm trong"):
        load_checksums(checksums)


def test_repo_checksums_file_is_valid() -> None:
    files = load_checksums()
    assert any(f.path == "yolov8n.pt" for f in files)
    for f in files:
        assert len(f.sha256) == 64
        assert f.url.startswith("https://")
