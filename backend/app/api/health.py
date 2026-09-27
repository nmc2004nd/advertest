"""GET /health: phiên bản, git commit, trạng thái Postgres và MinIO. Luôn trả 200."""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from functools import cache
from importlib.metadata import version
from pathlib import Path
from typing import Annotated, Protocol

import boto3
from botocore.config import Config
from fastapi import APIRouter, Depends
from sqlalchemy import create_engine, text

from advertest_contracts.models import DependencyStatus, HealthResponse

TIMEOUT_S = 2
_SHA1 = re.compile(r"^[0-9a-f]{40}$")
_REPO_ROOT = Path(__file__).resolve().parents[3]

router = APIRouter(tags=["health"])


class HealthChecks(Protocol):
    def postgres(self) -> DependencyStatus: ...
    def minio(self) -> DependencyStatus: ...


@dataclass(frozen=True)
class LiveChecks:
    """Kiểm tra kết nối thật. URL và khóa lấy từ biến môi trường."""

    def postgres(self) -> DependencyStatus:
        url = os.environ.get("DATABASE_URL")
        if not url:
            return DependencyStatus(ok=False, detail="Thiếu DATABASE_URL")
        engine = create_engine(url, connect_args={"connect_timeout": TIMEOUT_S})
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception as exc:
            return DependencyStatus(ok=False, detail=f"{type(exc).__name__}: {exc}"[:300])
        finally:
            engine.dispose()
        return DependencyStatus(ok=True)

    def minio(self) -> DependencyStatus:
        endpoint = os.environ.get("MINIO_ENDPOINT")
        if not endpoint:
            return DependencyStatus(ok=False, detail="Thiếu MINIO_ENDPOINT")
        client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=os.environ.get("MINIO_ACCESS_KEY"),
            aws_secret_access_key=os.environ.get("MINIO_SECRET_KEY"),
            config=Config(
                connect_timeout=TIMEOUT_S, read_timeout=TIMEOUT_S, retries={"max_attempts": 0}
            ),
        )
        try:
            client.list_buckets()
        except Exception as exc:
            return DependencyStatus(ok=False, detail=f"{type(exc).__name__}: {exc}"[:300])
        return DependencyStatus(ok=True)


def get_checks() -> HealthChecks:
    return LiveChecks()


@cache
def git_commit() -> str:
    """Ưu tiên biến GIT_COMMIT (image Docker không có .git); nếu không có thì hỏi git."""
    env_commit = os.environ.get("GIT_COMMIT", "").strip().lower()
    if _SHA1.fullmatch(env_commit):
        return env_commit
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_S,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return out if _SHA1.fullmatch(out) else "unknown"


@router.get("/health")
def health(checks: Annotated[HealthChecks, Depends(get_checks)]) -> HealthResponse:
    postgres = checks.postgres()
    minio = checks.minio()
    return HealthResponse(
        status="ok" if postgres.ok and minio.ok else "degraded",
        version=version("advertest"),
        git_commit=git_commit(),
        postgres=postgres,
        minio=minio,
    )
