"""Lệnh `advertest-worker` (plan.md Phase 3, task 29).

- `advertest-worker run [--once]`: lặp lease (5 giây khi rảnh) và chạy từng experiment.
  `--once`: xử lý tối đa một experiment rồi thoát.
- `advertest-worker calibrate --experiment <id>`: đo lại cost profile cho mọi attack của một
  experiment đang `running` thuộc target, gửi lên API (không lease, không chạy run).

Cấu hình qua biến môi trường (`config.py`).
"""

from __future__ import annotations

import logging
import time
from typing import Annotated
from uuid import UUID

import typer

from advertest_worker.cache import JobCache
from advertest_worker.client import WorkerClient
from advertest_worker.config import WorkerSettings
from advertest_worker.job import JobRunner
from ml_core.runner.env import default_device

app = typer.Typer(help="Worker của AdverTest: nhận job qua API nội bộ và chạy trên máy này.")


def _runner(settings: WorkerSettings) -> tuple[WorkerClient, JobRunner]:
    client = WorkerClient.connect(settings.api_url, settings.token)
    runner = JobRunner(
        client,
        JobCache(settings.cache_dir),
        settings.device or default_device(),
        heartbeat_interval_s=settings.heartbeat_interval_s,
    )
    return client, runner


def _logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


@app.command()
def run(
    once: Annotated[
        bool, typer.Option("--once", help="Xử lý tối đa một experiment rồi thoát")
    ] = False,
) -> None:
    """Nhận và chạy experiment của compute target gắn với WORKER_TOKEN."""
    _logging()
    settings = WorkerSettings.from_env()
    client, runner = _runner(settings)
    while True:
        lease = client.lease()
        if lease is not None:
            logging.info("Nhận experiment %s", lease.experiment_id)
            runner.run_lease(lease)
        if once:
            return
        if lease is None:
            time.sleep(settings.poll_interval_s)


@app.command()
def calibrate(
    experiment: Annotated[
        UUID, typer.Option("--experiment", help="Experiment đang running của target này")
    ],
) -> None:
    """Đo lại cost profile cho mọi attack của experiment và gửi lên API."""
    _logging()
    settings = WorkerSettings.from_env()
    client, runner = _runner(settings)
    bundle = client.bundle(experiment)
    loader = runner.cache.prepare(bundle)
    profiles = runner.calibrate_bundle(bundle, loader, force=True)
    for profile in profiles.values():
        typer.echo(
            f"{profile.attack_spec_id}: batch {profile.batch_size},"
            f" {profile.sec_per_image:.3f} s/ảnh, VRAM {profile.peak_vram_mb} MB"
        )
