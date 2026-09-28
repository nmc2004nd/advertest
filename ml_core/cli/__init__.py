"""CLI `advertest` của ML core.

File này chỉ đăng ký các nhóm lệnh của từng agent và định nghĩa `eval`, `viz` (Group 5).
Tùy chọn chung `--store-dir` chọn thư mục của `LocalStore`; store được đặt vào `ctx.obj`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, NoReturn
from uuid import UUID

import typer

from ml_core.cli.evaluate import DEFAULT_BATCH_SIZE, OutOfMemoryError, run_eval
from ml_core.cli.viz import run_viz
from ml_core.data.cli import dataset_app, mapping_app, slice_app
from ml_core.models.cli import app as model_app
from ml_core.runner.env import default_device
from ml_core.store import DEFAULT_STORE_DIR, KeyNotFoundError, LocalStore, require_store

app = typer.Typer(
    name="advertest",
    help="AdverTest ML core: đăng ký model, dataset, slice và đo metric.",
    no_args_is_help=True,
)
app.add_typer(model_app, name="model")
app.add_typer(dataset_app, name="dataset")
app.add_typer(slice_app, name="slice")
app.add_typer(mapping_app, name="mapping")


@app.callback()
def main(
    ctx: typer.Context,
    store_dir: Annotated[
        Path, typer.Option("--store-dir", help="Thư mục của kho artifact local.")
    ] = DEFAULT_STORE_DIR,
) -> None:
    ctx.obj = LocalStore(store_dir)


def _fail(exc: BaseException) -> NoReturn:
    message = exc.args[0] if exc.args else str(exc)
    typer.echo(f"Lỗi: {message}", err=True)
    raise typer.Exit(code=1) from exc


@app.command("eval")
def eval_(
    ctx: typer.Context,
    model: Annotated[UUID, typer.Option("--model", help="id của model")],
    slice_id: Annotated[UUID, typer.Option("--slice", help="id của slice")],
    mapping: Annotated[UUID, typer.Option("--mapping", help="id của class mapping")],
    out: Annotated[Path, typer.Option("--out", help="File JSON CleanEvalResult")],
    device: Annotated[
        str | None, typer.Option("--device", help="Ví dụ cpu, cuda:0; mặc định GPU nếu có")
    ] = None,
    batch_size: Annotated[int, typer.Option("--batch-size", min=1)] = DEFAULT_BATCH_SIZE,
) -> None:
    """Đo mAP của model trên slice (ảnh sạch), xuất CleanEvalResult."""
    store = require_store(ctx.obj)
    try:
        run = run_eval(store, model, slice_id, mapping, device or default_device(), batch_size)
    except (KeyNotFoundError, FileNotFoundError, ValueError, OutOfMemoryError) as exc:
        _fail(exc)
    for warning in run.warnings:
        typer.echo(f"Cảnh báo: {warning}", err=True)
    result = run.result
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(result.model_dump_json(indent=2) + "\n")
    typer.echo(
        f"mAP@0.5 = {result.metrics.map50:.4f}, mAP@0.5:0.95 = {result.metrics.map50_95:.4f}, "
        f"{result.num_images} ảnh, cache {'hit' if result.cache.hit else 'miss'}, "
        f"{result.timing.sec_per_image:.4f} s/ảnh, {result.device} → {out}"
    )


@app.command("viz")
def viz(
    ctx: typer.Context,
    slice_id: Annotated[UUID, typer.Option("--slice", help="id của slice")],
    mapping: Annotated[UUID, typer.Option("--mapping", help="id của class mapping")],
    model: Annotated[UUID, typer.Option("--model", help="id của model")],
    out: Annotated[Path, typer.Option("--out", help="Thư mục xuất PNG")],
    n: Annotated[int, typer.Option("--n", min=1, help="Số ảnh")] = 8,
    device: Annotated[
        str | None, typer.Option("--device", help="Ví dụ cpu, cuda:0; mặc định GPU nếu có")
    ] = None,
) -> None:
    """Vẽ ground truth (xanh), prediction (đỏ), ignore region (xám) lên ảnh letterbox, xuất PNG."""
    store = require_store(ctx.obj)
    try:
        paths = run_viz(store, model, slice_id, mapping, n, out, device or default_device())
    except (KeyNotFoundError, FileNotFoundError, ValueError) as exc:
        _fail(exc)
    typer.echo(f"Đã ghi {len(paths)} ảnh vào {out}")
