"""Môi trường chạy: git commit, thiết bị, phiên bản thư viện (dùng chung cho `eval` và `run`)."""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import torch

from advertest_contracts.models import Environment

REPO_ROOT = Path(__file__).resolve().parents[2]
DIRTY_WARNING = "Working tree có thay đổi chưa commit; git_commit không mô tả đủ mã đã chạy"
# Log phiên làm việc được git theo dõi và đổi liên tục; không tính là thay đổi mã
# (requirements.md Phase 2, mục Fingerprint và manifest).
_DIRTY_PATHSPEC = (".", ":(exclude).ai-log")
_GIT_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_DOCKER_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


@dataclass(frozen=True)
class GitState:
    commit: str
    dirty: bool


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


def git_state() -> GitState:
    """Commit của mã đang chạy: biến `GIT_COMMIT` nếu có (image Docker không có `.git`, coi như
    sạch), không thì `git rev-parse HEAD`; `dirty` khi có thay đổi chưa commit ngoài `.ai-log/`."""
    env = os.environ.get("GIT_COMMIT", "").strip()
    if env:
        if not _GIT_COMMIT.fullmatch(env):
            raise ValueError(f"GIT_COMMIT không phải commit hash 40 ký tự: {env!r}")
        return GitState(commit=env, dirty=False)
    try:
        commit = _git("rev-parse", "HEAD")
        status = _git("status", "--porcelain", "--untracked-files=no", "--", *_DIRTY_PATHSPEC)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValueError("Không xác định được git commit; đặt biến GIT_COMMIT") from exc
    return GitState(commit=commit, dirty=bool(status))


def current_git_commit() -> tuple[str, list[str]]:
    """Commit và cảnh báo (nếu working tree có thay đổi chưa commit)."""
    state = git_state()
    return state.commit, [DIRTY_WARNING] if state.dirty else []


def default_device() -> str:
    return "cuda:0" if torch.cuda.is_available() else "cpu"


def describe_device(device: str) -> str:
    """Ví dụ `cuda:0 (NVIDIA GeForce RTX 3050)` hoặc `cpu`."""
    torch_device = torch.device(device)
    if torch_device.type != "cuda":
        return torch_device.type
    index = torch_device.index if torch_device.index is not None else torch.cuda.current_device()
    return f"cuda:{index} ({torch.cuda.get_device_name(index)})"


def _driver_version() -> str | None:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    lines = out.strip().splitlines()
    return lines[0].strip() if lines else None


def environment(device: str) -> Environment:
    """Máy đã chạy run (không thuộc fingerprint). Chạy bằng CLI nên `compute_target_id = null`."""
    torch_device = torch.device(device)
    if torch_device.type != "cuda":
        return Environment(
            compute_target_id=None, gpu_model=None, cuda_version=None, driver_version=None
        )
    index = torch_device.index if torch_device.index is not None else torch.cuda.current_device()
    return Environment(
        compute_target_id=None,
        gpu_model=torch.cuda.get_device_name(index),
        cuda_version=torch.version.cuda,
        driver_version=_driver_version(),
    )


def docker_image_digest() -> str:
    """Biến `DOCKER_IMAGE_DIGEST` (đặt trong image Docker), không có thì `"none"`."""
    digest = os.environ.get("DOCKER_IMAGE_DIGEST", "").strip()
    if not digest:
        return "none"
    if not _DOCKER_DIGEST.fullmatch(digest):
        raise ValueError(f"DOCKER_IMAGE_DIGEST không đúng dạng sha256:<64 hex>: {digest!r}")
    return digest
