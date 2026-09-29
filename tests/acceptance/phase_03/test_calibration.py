"""Calibration và ước lượng (validation.md Phase 3, test_calibration.py)."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

import httpx
import pytest
import yaml
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from advertest_worker import cli as worker_cli
from backend.app.db import models as m
from backend.app.services.estimate import estimate_seconds

from .conftest import ADMIN, Harness, LiveApi, World, admin

pytestmark = pytest.mark.db


def _profiles(harness: Harness, target: str) -> list[m.CostProfile]:
    with Session(harness.app_engine) as session:
        target_id = session.query(m.ComputeTarget).filter_by(name=target).one().id
        return list(session.query(m.CostProfile).filter_by(compute_target_id=target_id))


def test_calibrate_command_on_cpu(
    harness: Harness, live_api: LiveApi, world: World, tmp_path_factory: pytest.TempPathFactory
) -> None:
    name, token = harness.target()
    experiment_id = harness.submit(name, harness.world.config({"fgsm": [4]}))
    lease = httpx.post(
        f"{live_api.url}/internal/worker/lease", headers={"Authorization": f"Bearer {token}"}
    )
    assert lease.status_code == 200 and lease.json()["experiment_id"] == str(experiment_id)
    result = CliRunner().invoke(
        worker_cli.app,
        ["calibrate", "--experiment", str(experiment_id)],
        env={
            "API_URL": live_api.url,
            "WORKER_TOKEN": token,
            "CACHE_DIR": str(tmp_path_factory.mktemp("calibrate-cache")),
            "DEVICE": "cpu",
        },
    )
    assert result.exit_code == 0, result.output
    (profile,) = _profiles(harness, name)
    assert str(profile.model_version_id) == world.model_id
    n = min(20, len(world.image_ids))  # fixture 5 ảnh: n = 5
    assert 1 <= profile.batch_size <= min(n, 32)
    assert profile.sec_per_image > 0 and profile.peak_vram_mb == 0
    assert profile.environment is not None and profile.environment["gpu_model"] is None


def test_job_without_profile_calibrates_first_then_uses_profile_batch(harness: Harness) -> None:
    name, token = harness.target()
    experiment_id = harness.submit(name, harness.world.config({"fgsm": [4]}, seed=21))
    sizes: list[int] = []

    def hook(_run_id: UUID, ids: Sequence[str]) -> None:
        sizes.append(len(ids))

    harness.work(token, experiment_id, on_batch=hook)
    (profile,) = _profiles(harness, name)
    total = len(harness.world.image_ids)
    expected = [profile.batch_size] * (total // profile.batch_size)
    if total % profile.batch_size:
        expected.append(total % profile.batch_size)
    assert sizes == expected


def test_estimate(harness: Harness) -> None:
    a, b = UUID(int=1), UUID(int=2)
    profiles = {a: m.CostProfile(sec_per_image=0.5), b: m.CostProfile(sec_per_image=2.0)}
    runs = [(a, 300), (a, 300), (b, 300)]
    # (300 * 0.5 + 300 * 0.5 + 300 * 2.0) * 1.2 = 1080
    assert estimate_seconds(runs, profiles) == pytest.approx(1080.0)
    assert estimate_seconds([(UUID(int=3), 10)], profiles) is None

    name, _ = harness.target()
    config = harness.tmp / "estimate.yaml"
    config.write_text(yaml.safe_dump(harness.world.config({"fgsm": [4]})))
    out = admin(harness.cli_env, "submit", "--config", str(config), "--target", name, "--as", ADMIN)
    assert "chưa có ước lượng" in out.output
