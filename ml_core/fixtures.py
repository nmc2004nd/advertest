"""Tải fixture test (ảnh KITTI, weights YOLOv8n) và kiểm tra sha256.

Danh sách file nằm trong `tests/fixtures/checksums.json`:

    {
      "base_url": "https://.../",              # dùng khi một file không có "url" riêng
      "files": [{"path": "...", "sha256": "...", "url": "..."}]
    }

Fixture không commit vào repo; file chỉ được đặt vào đúng chỗ khi sha256 khớp.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
CHECKSUMS_FILE = FIXTURES_DIR / "checksums.json"
TIMEOUT_S = 60


@dataclass(frozen=True)
class FixtureFile:
    path: str
    sha256: str
    url: str


class FixtureError(Exception):
    pass


def load_checksums(checksums_file: Path = CHECKSUMS_FILE) -> list[FixtureFile]:
    data = json.loads(checksums_file.read_text())
    base_url = data.get("base_url", "")
    files = []
    for entry in data["files"]:
        path = entry["path"]
        if Path(path).is_absolute() or ".." in Path(path).parts:
            raise FixtureError(f"Đường dẫn fixture phải nằm trong tests/fixtures: {path}")
        url = entry.get("url") or urljoin(base_url, path)
        if not url:
            raise FixtureError(f"Không có URL cho {path} (thiếu cả url lẫn base_url)")
        files.append(FixtureFile(path=path, sha256=entry["sha256"].lower(), url=url))
    return files


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, dest: Path) -> None:
    with urllib.request.urlopen(url, timeout=TIMEOUT_S) as response, dest.open("wb") as out:
        while chunk := response.read(1 << 20):
            out.write(chunk)


def fetch_one(item: FixtureFile, root: Path = FIXTURES_DIR) -> bool:
    """Tải một file nếu chưa có hoặc sai checksum. Trả True nếu vừa tải."""
    target = root / item.path
    if target.is_file() and sha256_file(target) == item.sha256:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.")
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        _download(item.url, tmp)
        actual = sha256_file(tmp)
        if actual != item.sha256:
            raise FixtureError(
                f"sha256 không khớp cho {item.path}: cần {item.sha256}, nhận {actual}"
            )
        tmp.replace(target)
    finally:
        tmp.unlink(missing_ok=True)
    return True


def fetch_all(checksums_file: Path = CHECKSUMS_FILE, root: Path = FIXTURES_DIR) -> list[str]:
    """Tải mọi fixture; báo lỗi gộp nếu có file không tải được hoặc sai checksum."""
    errors = []
    downloaded = []
    for item in load_checksums(checksums_file):
        try:
            if fetch_one(item, root):
                downloaded.append(item.path)
        except (OSError, FixtureError) as exc:
            errors.append(f"{item.path}: {exc}")
    if errors:
        raise FixtureError("Không tải được fixture:\n" + "\n".join(errors))
    return downloaded
