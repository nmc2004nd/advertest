"""CLI `advertest` của ML core.

File này chỉ đăng ký các nhóm lệnh của từng agent và định nghĩa `eval`, `viz` (Group 5).
Tùy chọn chung `--store-dir` chọn thư mục của `LocalStore`; store được đặt vào `ctx.obj`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated
from uuid import UUID

import typer

from ml_core.data.cli import dataset_app, mapping_app, slice_app
from ml_core.models.cli import app as model_app
from ml_core.store import DEFAULT_STORE_DIR, LocalStore

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


def _not_implemented(command: str) -> None:
    typer.echo(f"Lệnh `{command}` chưa có (Phase 1 Group 5).", err=True)
    raise typer.Exit(code=1)


@app.command("eval")
def eval_(
    model: Annotated[UUID, typer.Option("--model", help="id của model")],
    slice_id: Annotated[UUID, typer.Option("--slice", help="id của slice")],
    mapping: Annotated[UUID, typer.Option("--mapping", help="id của class mapping")],
    out: Annotated[Path, typer.Option("--out", help="File JSON CleanEvalResult")],
    device: Annotated[str | None, typer.Option("--device", help="Ví dụ cpu, cuda:0")] = None,
    batch_size: Annotated[int | None, typer.Option("--batch-size", min=1)] = None,
) -> None:
    """Đo mAP của model trên slice (ảnh sạch), xuất CleanEvalResult."""
    _not_implemented("eval")


@app.command("viz")
def viz(
    slice_id: Annotated[UUID, typer.Option("--slice", help="id của slice")],
    mapping: Annotated[UUID, typer.Option("--mapping", help="id của class mapping")],
    model: Annotated[UUID, typer.Option("--model", help="id của model")],
    out: Annotated[Path, typer.Option("--out", help="Thư mục xuất PNG")],
    n: Annotated[int, typer.Option("--n", min=1, help="Số ảnh")] = 8,
) -> None:
    """Vẽ ground truth, prediction và ignore region lên ảnh letterbox, xuất PNG."""
    _not_implemented("viz")
