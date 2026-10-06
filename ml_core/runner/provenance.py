"""Nguồn gốc mã và môi trường cho fingerprint: git, phiên bản thư viện, digest image Docker.

Là seam chính thức của Phase R1: CLI (`Runner`, `run_config`) và worker (`JobRunner`) nhận một
`Provenance` qua tham số thay vì để test patch `git_state` ở cấp module.
"""

from __future__ import annotations

from typing import Protocol

from advertest_contracts.models import LibVersions
from ml_core.models.register import lib_versions
from ml_core.runner.env import GitState, docker_image_digest, git_state


class Provenance(Protocol):
    def git(self) -> GitState: ...

    def lib_versions(self) -> LibVersions: ...

    def docker_image_digest(self) -> str: ...


class EnvProvenance:
    """Cài đặt mặc định: biến môi trường `GIT_COMMIT`, `DOCKER_IMAGE_DIGEST` và repo git
    (xem `ml_core/runner/env.py`), phiên bản thư viện đang nạp."""

    def git(self) -> GitState:
        return git_state()

    def lib_versions(self) -> LibVersions:
        return lib_versions()

    def docker_image_digest(self) -> str:
        return docker_image_digest()
