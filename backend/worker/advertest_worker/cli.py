"""Lệnh `advertest-worker` (plan.md Phase 3, task 29).

- `advertest-worker run [--once]`: lặp lease (5 giây khi rảnh) và chạy từng experiment.
  `--once`: xử lý tối đa một experiment rồi thoát.
- `advertest-worker calibrate --experiment <id>`: đo lại cost profile cho mọi attack của một
  experiment đang `running` thuộc target, gửi lên API (không lease, không chạy run).
- `advertest-worker --tools [--once]` (Phase R2): process riêng chỉ lease job công cụ
  (`spec_check`, `model_check`, `quick_try`), lặp `ToolRunner.run_next`.

Cấu hình qua biến môi trường (`config.py`).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Annotated
from uuid import UUID

import typer

from advertest_worker.cache import JobCache
from advertest_worker.client import WorkerClient
from advertest_worker.config import WorkerSettings
from advertest_worker.job import JobRunner
from advertest_worker.tools import ToolRunner
from ml_core.runner.env import default_device

logger = logging.getLogger(__name__)
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


def serve(
    client: WorkerClient,
    runner: JobRunner,
    *,
    once: bool = False,
    poll_interval_s: float,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Vòng lặp lease → chạy. Lỗi của một job (hoặc API tạm không gọi được sau khi client đã
    retry) chỉ được ghi log; worker chờ rồi tiếp tục, không thoát."""
    while True:
        lease = None
        try:
            lease = client.lease()
            if lease is not None:
                logger.info("Nhận experiment %s", lease.experiment_id)
                runner.run_lease(lease)
        except Exception:
            logger.exception(
                "Lỗi khi nhận hoặc chạy experiment %s", lease.experiment_id if lease else "-"
            )
            lease = None  # chờ trước khi thử lại
        if once:
            return
        if lease is None:
            sleep(poll_interval_s)


def serve_tools(
    runner: ToolRunner,
    *,
    once: bool = False,
    poll_interval_s: float,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Vòng lặp của `--tools`: chạy job kế tiếp, chờ khi hết job. Lỗi chỉ được ghi log."""
    while True:
        try:
            ran = runner.run_next()
        except Exception:
            logger.exception("Lỗi khi nhận hoặc chạy job công cụ")
            ran = False  # chờ trước khi thử lại
        if once:
            return
        if not ran:
            sleep(poll_interval_s)


def _logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    tools: Annotated[
        bool, typer.Option("--tools", help="Chỉ nhận job công cụ (kiểm tra spec, model, thử nhanh)")
    ] = False,
    once: Annotated[
        bool, typer.Option("--once", help="Với --tools: xử lý tối đa một job rồi thoát")
    ] = False,
) -> None:
    """Worker của AdverTest."""
    if ctx.invoked_subcommand is not None:
        if tools or once:
            raise typer.BadParameter("--tools và --once không dùng cùng lệnh con (run, calibrate)")
        return
    if not tools:
        typer.echo(ctx.get_help())
        raise typer.Exit(0)
    _logging()
    settings = WorkerSettings.from_env()
    runner = ToolRunner(
        WorkerClient.connect(settings.api_url, settings.token),
        JobCache(settings.cache_dir),
        settings.device or default_device(),
        heartbeat_interval_s=settings.heartbeat_interval_s,
    )
    serve_tools(runner, once=once, poll_interval_s=settings.poll_interval_s)


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
    serve(client, runner, once=once, poll_interval_s=settings.poll_interval_s)


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
