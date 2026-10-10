"""Kiểm fixture đã chép vào image worker theo tests/fixtures/checksums.json (Phase R3).

`spec_check` và `model_check` của worker công cụ cần ảnh KITTI fixture, nhãn và `yolov8n.pt`.
Thiếu file hoặc sha256 lệch thì thoát mã 1 để `docker build` fail.

Cách dùng: python check_fixtures.py <thư mục fixtures>
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

# Chỉ các fixture mà worker công cụ dùng; checksums.json còn có fixture riêng của test.
NEEDED = ("yolov8n.pt", "kitti/")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(root: Path) -> int:
    entries = json.loads((root / "checksums.json").read_text())["files"]
    needed = [e for e in entries if e["path"].startswith(NEEDED)]
    errors = []
    for entry in needed:
        path = root / entry["path"]
        if not path.is_file():
            errors.append(f"thiếu {entry['path']}")
        elif _sha256(path) != entry["sha256"].lower():
            errors.append(f"sha256 lệch: {entry['path']}")
    if not needed or errors:
        print("Fixture của worker không hợp lệ (chạy make fixtures):", *errors, sep="\n  ")
        return 1
    print(f"Fixture của worker: {len(needed)} file, sha256 khớp.")
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
