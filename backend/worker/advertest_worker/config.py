"""Cấu hình worker qua biến môi trường (plan.md Phase 3, task 22).

- `API_URL`: gốc của API (ví dụ `http://127.0.0.1:8000`); worker gọi `<API_URL>/internal/worker/`.
- `WORKER_TOKEN`: token của compute target (in ra một lần khi tạo hoặc xoay).
- `CACHE_DIR`: cache weights, ảnh, manifest theo sha256 (mặc định `~/.cache/advertest-worker`).
- `DEVICE`: ví dụ `cpu`, `cuda:0`; mặc định GPU nếu có.

Worker không có thông tin đăng nhập Postgres hay MinIO (requirements.md Phase 3, Decisions).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CACHE_DIR = Path.home() / ".cache" / "advertest-worker"
POLL_INTERVAL_S = 5.0  # gọi lease khi rảnh
HEARTBEAT_INTERVAL_S = 15.0


@dataclass(frozen=True)
class WorkerSettings:
    api_url: str
    token: str
    cache_dir: Path = DEFAULT_CACHE_DIR
    device: str | None = None
    poll_interval_s: float = POLL_INTERVAL_S
    heartbeat_interval_s: float = HEARTBEAT_INTERVAL_S

    @classmethod
    def from_env(cls) -> WorkerSettings:
        api_url = os.environ.get("API_URL", "").strip()
        token = os.environ.get("WORKER_TOKEN", "").strip()
        if not api_url or not token:
            raise RuntimeError("Cần biến môi trường API_URL và WORKER_TOKEN")
        cache = os.environ.get("CACHE_DIR", "").strip()
        return cls(
            api_url=api_url.rstrip("/"),
            token=token,
            cache_dir=Path(cache) if cache else DEFAULT_CACHE_DIR,
            device=os.environ.get("DEVICE", "").strip() or None,
        )
