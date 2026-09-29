"""docker/compose.yaml cho Phase 3 (validation.md: ranh giới kiến trúc; plan.md task 32)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

COMPOSE = Path(__file__).resolve().parents[3] / "docker" / "compose.yaml"
WORKERS = ("worker", "worker-cpu")
SECRET = re.compile(r"PASSWORD|MINIO_ACCESS_KEY|MINIO_SECRET_KEY|DATABASE_URL|postgres", re.I)


def _services() -> dict[str, Any]:
    services: dict[str, Any] = yaml.safe_load(COMPOSE.read_text())["services"]
    return services


def test_worker_services_have_no_db_or_minio_credentials() -> None:
    services = _services()
    for name in WORKERS:
        worker = services[name]
        env: dict[str, str] = worker["environment"]
        assert set(env) == {"API_URL", "WORKER_TOKEN", "CACHE_DIR", "DEVICE", "DOCKER_IMAGE_DIGEST"}
        for key, value in env.items():
            assert not SECRET.search(key) and not SECRET.search(str(value)), (name, key)
        assert "depends_on" not in worker and "ports" not in worker
        assert worker["entrypoint"] == ["advertest-worker", "run"]


def test_worker_profiles_and_torch_variants() -> None:
    services = _services()
    assert services["worker-cpu"]["profiles"] == ["cpu"]
    assert services["worker-cpu"]["build"]["args"]["TORCH"] == "cpu"
    assert services["worker"]["profiles"] == ["gpu"]
    assert services["worker"]["build"]["args"]["TORCH"] == "cuda"
    devices = services["worker"]["deploy"]["resources"]["reservations"]["devices"]
    assert devices[0]["driver"] == "nvidia"


def test_minio_s3_port_bound_to_localhost_and_api_signs_for_it() -> None:
    services = _services()
    assert "127.0.0.1:${MINIO_PORT:-9000}:9000" in services["minio"]["ports"]
    assert all(p.startswith("127.0.0.1:") for s in services.values() for p in s.get("ports", []))
    assert "MINIO_PUBLIC_ENDPOINT" in services["api"]["environment"]
    assert "ports" not in services["postgres"]
