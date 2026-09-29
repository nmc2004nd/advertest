"""CLI quản trị phía server `advertest-admin` (requirements.md Phase 3, CLI quản trị; plan.md
task 31). Chạy trong container `api` (có DATABASE_URL và khóa MinIO của API):

    docker compose exec api advertest-admin <lệnh>

Lệnh ghi dữ liệu nhận `--as <email>`: người dùng đó phải là admin `active`, và là actor trong
`audit_log`. Phase này chưa có endpoint công khai cho experiment: gửi và theo dõi qua CLI này.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from typing import Annotated
from uuid import UUID

import typer
from sqlalchemy import select
from sqlalchemy.orm import Session

from advertest_contracts.enums import ExperimentStatus
from backend.app.db import models as m
from backend.app.db.engine import make_engine
from backend.app.services import audit, compute_targets, estimate, experiments, registry
from backend.app.services.errors import ServiceError
from backend.app.storage import Buckets, make_s3_client
from ml_core.runner.config import load_config
from ml_core.store import LocalStore

app = typer.Typer(help="Quản trị AdverTest phía server (compute target, dữ liệu, experiment).")
target_app = typer.Typer(help="Compute target và token của worker.")
experiment_app = typer.Typer(help="Theo dõi và hủy experiment.")
app.add_typer(target_app, name="compute-target")
app.add_typer(experiment_app, name="experiment")

WATCH_INTERVAL_S = 2.0
TERMINAL = (ExperimentStatus.COMPLETED, ExperimentStatus.CANCELLED)
_sleep: Callable[[float], None] = time.sleep  # test thay được

ActorOpt = Annotated[str, typer.Option("--as", help="Email của admin thực hiện (ghi audit)")]


@contextmanager
def _transaction() -> Iterator[Session]:
    """Một transaction; lỗi nghiệp vụ in ra stderr và thoát mã 1."""
    try:
        with Session(make_engine()) as session, session.begin():
            yield session
    except ServiceError as exc:
        typer.echo(f"Lỗi: {exc}", err=True)
        raise typer.Exit(code=1) from exc


# ---------------------------------------------------------------- compute target


@target_app.command("create")
def target_create(
    name: Annotated[str, typer.Option("--name", help="Tên target, ví dụ local-dev")],
    actor: ActorOpt,
    gpu_model: Annotated[str | None, typer.Option("--gpu-model")] = None,
    vram_gb: Annotated[float | None, typer.Option("--vram-gb")] = None,
    time_limit: Annotated[
        int, typer.Option("--time-limit", help="Giới hạn thời gian mặc định (giây)")
    ] = compute_targets.DEFAULT_TIME_LIMIT_S,
    kind: Annotated[str, typer.Option("--kind", help="Phase 3 chỉ nhận local")] = "local",
) -> None:
    """Tạo compute target và in token một lần duy nhất (DB chỉ lưu sha256)."""
    with _transaction() as session:
        admin = audit.require_admin(session, actor)
        if kind != "local":
            raise ServiceError("Phase 3 chỉ nhận --kind local")
        issued = compute_targets.create(
            session,
            actor=admin,
            name=name,
            gpu_model=gpu_model,
            vram_gb=Decimal(str(vram_gb)) if vram_gb is not None else None,
            time_limit_s=time_limit,
        )
        target_id = issued.target.id
    typer.echo(f"Đã tạo compute target {name} ({target_id}).")
    typer.echo("Token (chỉ hiện một lần, đặt vào WORKER_TOKEN của worker):")
    typer.echo(issued.token)


@target_app.command("rotate-token")
def target_rotate(name: Annotated[str, typer.Argument(help="Tên target")], actor: ActorOpt) -> None:
    """Cấp token mới; token cũ mất hiệu lực ngay."""
    with _transaction() as session:
        admin = audit.require_admin(session, actor)
        issued = compute_targets.rotate_token(session, actor=admin, name=name)
    typer.echo(f"Đã cấp token mới cho {name}; token cũ không còn dùng được.")
    typer.echo("Token (chỉ hiện một lần):")
    typer.echo(issued.token)


@target_app.command("list")
def target_list() -> None:
    with _transaction() as session:
        for target in compute_targets.list_targets(session):
            token = "có token" if target.token_hash else "chưa có token (rotate-token)"
            heartbeat = target.last_heartbeat_at.isoformat() if target.last_heartbeat_at else "-"
            typer.echo(
                f"{target.name}\t{target.kind}\t{target.gpu_model or '-'}\t"
                f"{target.default_time_limit_s}s\t{token}\theartbeat {heartbeat}"
            )


# ---------------------------------------------------------------- dữ liệu


@app.command("import-local")
def import_local(
    store: Annotated[Path, typer.Option("--store", help="Thư mục LocalStore", exists=True)],
    actor: ActorOpt,
) -> None:
    """Đăng ký model, dataset, slice, mapping từ LocalStore vào DB và MinIO (chỉ ảnh của slice)."""
    with _transaction() as session:
        admin = audit.require_admin(session, actor)
        report = registry.import_local(
            session, LocalStore(store), Buckets.from_client(make_s3_client()), actor=admin
        )
    typer.echo(
        f"Model: {len(report.models)}, dataset: {len(report.datasets)},"
        f" mapping: {len(report.mappings)}, slice: {len(report.slices)};"
        f" ảnh mới upload: {report.images_uploaded}, đã có: {report.images_present}."
    )


# ---------------------------------------------------------------- experiment


def _format_seconds(seconds: float | None) -> str:
    if seconds is None:
        return "chưa có ước lượng"
    minutes, secs = divmod(round(seconds), 60)
    return f"{minutes} phút {secs} giây" if minutes else f"{secs} giây"


@app.command("submit")
def submit(
    config: Annotated[Path, typer.Option("--config", help="File YAML LocalRunConfig", exists=True)],
    target: Annotated[str, typer.Option("--target", help="Tên compute target")],
    actor: ActorOpt,
    time_limit: Annotated[
        int | None, typer.Option("--time-limit", help="Giây; mặc định theo target")
    ] = None,
) -> None:
    """Tạo experiment queued (protocol dev-open); `device`, `batch_size` của YAML bị bỏ qua."""
    run_config = load_config(config)
    with _transaction() as session:
        admin = audit.require_admin(session, actor)
        experiment = experiments.submit(
            session,
            actor=admin,
            config=run_config,
            target=compute_targets.get_by_name(session, target),
            time_limit_s=time_limit,
        )
        planned = len(experiments.runs_of(session, experiment.id))
        seconds = estimate.estimate_experiment(session, experiment)
        experiment_id, limit = experiment.id, experiment.limit_value
    typer.echo(f"Experiment {experiment_id}: {planned} run, giới hạn {limit:.0f} giây.")
    typer.echo(f"Ước lượng thời gian: {_format_seconds(seconds)}")


@experiment_app.command("list")
def experiment_list() -> None:
    with _transaction() as session:
        rows = session.execute(
            select(m.Experiment, m.ComputeTarget.name)
            .join(m.ComputeTarget, m.ComputeTarget.id == m.Experiment.compute_target_id)
            .order_by(m.Experiment.submitted_at.desc())
        ).all()
        for experiment, target_name in rows:
            submitted = experiment.submitted_at.isoformat() if experiment.submitted_at else "-"
            typer.echo(f"{experiment.id}\t{experiment.status}\t{target_name}\t{submitted}")


def _show(session: Session, experiment_id: UUID) -> ExperimentStatus:
    experiment = experiments.get(session, experiment_id)
    target = session.get_one(m.ComputeTarget, experiment.compute_target_id)
    names = {
        spec_id: name
        for spec_id, name in session.execute(select(m.AttackSpecRow.id, m.AttackSpecRow.name))
    }
    used = experiment.processing_seconds_used
    typer.echo(f"Experiment {experiment.id}  [{experiment.status}]  target {target.name}")
    typer.echo(
        f"Thời gian xử lý: {used:.1f}/{experiment.limit_value:.0f} giây"
        f"  ước lượng: {_format_seconds(estimate.estimate_experiment(session, experiment))}"
    )
    for run in experiments.runs_of(session, experiment.id):
        reason = run.status_reason or {}
        note = f" ({reason.get('code')}: {reason.get('message')})" if reason else ""
        typer.echo(
            f"  #{run.ordinal} {names.get(run.attack_spec_id, run.attack_spec_id)}"
            f" {run.level:g}: {run.status}{note}  {run.images_done}/{run.images_total} ảnh"
            f"  {run.gpu_seconds:.1f} s"
        )
    return experiment.status


@experiment_app.command("show")
def experiment_show(
    experiment_id: Annotated[UUID, typer.Argument(help="Id experiment")],
    watch: Annotated[
        bool, typer.Option("--watch", help="Làm mới mỗi 2 giây tới khi experiment kết thúc")
    ] = False,
) -> None:
    """Trạng thái experiment, từng run, tiến độ, thời gian đã dùng."""
    while True:
        with _transaction() as session:
            status = _show(session, experiment_id)
        if not watch or status in TERMINAL:
            return
        _sleep(WATCH_INTERVAL_S)
        typer.echo("")


@experiment_app.command("cancel")
def experiment_cancel(
    experiment_id: Annotated[UUID, typer.Argument(help="Id experiment")], actor: ActorOpt
) -> None:
    """Hủy experiment; worker dừng sau batch hiện tại."""
    with _transaction() as session:
        admin = audit.require_admin(session, actor)
        experiment = experiments.cancel(session, actor=admin, experiment_id=experiment_id)
        status = experiment.status
    typer.echo(f"Experiment {experiment_id}: {status}")


def main() -> None:
    app()
