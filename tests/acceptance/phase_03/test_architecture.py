"""Ranh giới kiến trúc (validation.md Phase 3, test_architecture.py). Không cần DB."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[3]
PACKAGES = {
    "advertest_worker": REPO / "backend" / "worker" / "advertest_worker",
    "ml_core": REPO / "ml_core",
    "attacks": REPO / "attacks",
}
FORBIDDEN = ("backend", "sqlalchemy", "boto3", "botocore", "psycopg", "alembic")
CREDENTIAL = re.compile(r"PASSWORD|MINIO_ACCESS_KEY|MINIO_SECRET_KEY|DATABASE_URL|postgres", re.I)
WRITE_METHODS = {"post", "put", "patch", "delete"}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


def test_worker_ml_core_attacks_do_not_import_db_or_minio_clients() -> None:
    offenders = []
    for package, root in PACKAGES.items():
        files = [p for p in root.rglob("*.py") if "tests" not in p.relative_to(root).parts]
        assert files, package
        for path in files:
            for name in _imports(path):
                if name.split(".")[0] in FORBIDDEN:
                    offenders.append(f"{path.relative_to(REPO)}: {name}")
    assert offenders == []


def test_compose_worker_env_has_no_db_or_minio_credentials() -> None:
    services = yaml.safe_load((REPO / "docker" / "compose.yaml").read_text())["services"]
    workers = [
        name for name, s in services.items() if "advertest-worker" in s.get("entrypoint", [])
    ]
    assert set(workers) == {"worker", "worker-cpu"}
    for name in workers:
        for key, value in services[name]["environment"].items():
            assert not CREDENTIAL.search(key) and not CREDENTIAL.search(str(value)), (name, key)


def test_no_public_endpoint_writes_runs_or_failure_cases() -> None:
    openapi = json.loads((REPO / "contracts" / "openapi.json").read_text())
    for path, ops in openapi["paths"].items():
        if path.startswith("/internal/worker"):
            continue
        if "/runs" in path or "/failure-cases" in path:
            assert not WRITE_METHODS & set(ops), path
    # Chỉ router của worker dùng service ghi kết quả run.
    api_dir = REPO / "backend" / "app" / "api"
    for path in api_dir.glob("*.py"):
        uses_runs = "backend.app.services.runs" in _imports(path) or any(
            "runs" in (alias.name for alias in node.names)
            for node in ast.walk(ast.parse(path.read_text()))
            if isinstance(node, ast.ImportFrom) and node.module == "backend.app.services"
        )
        assert not uses_runs or path.name == "worker.py", path.name
