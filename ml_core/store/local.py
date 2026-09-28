"""`ArtifactStore` trên đĩa local."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from ml_core.store.base import KeyConflictError, KeyNotFoundError, validate_key

DEFAULT_STORE_DIR = Path(__file__).resolve().parents[2] / "data" / "store"


class LocalStore:
    def __init__(self, root: Path = DEFAULT_STORE_DIR) -> None:
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        return self.root.joinpath(*validate_key(key).split("/"))

    def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        if path.is_file():
            if path.read_bytes() != data:
                raise KeyConflictError(f"Key {key!r} đã có với nội dung khác")
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        # Ghi vào file tạm cùng thư mục rồi đổi tên: người đọc không bao giờ thấy file dở dang.
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def get(self, key: str) -> bytes:
        path = self._path(key)
        if not path.is_file():
            raise KeyNotFoundError(key)
        return path.read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def list(self, prefix: str = "") -> list[str]:
        if not self.root.is_dir():
            return []
        keys = (
            p.relative_to(self.root).as_posix()
            for p in self.root.rglob("*")
            if p.is_file() and not p.name.startswith(".tmp-")
        )
        return sorted(k for k in keys if k.startswith(prefix))
