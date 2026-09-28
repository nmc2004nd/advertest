"""Lệnh CLI của ml-model: `advertest model register`.

Lấy store trong lệnh bằng `ml_core.store.require_store(ctx.obj)`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ml_core.models.register import load_check_images, register_model
from ml_core.store import require_store

app = typer.Typer(help="Đăng ký và xem model.", no_args_is_help=True)


@app.command("register")
def register(
    ctx: typer.Context,
    weights: Annotated[
        Path, typer.Option("--weights", exists=True, dir_okay=False, help="File weights (.pt)")
    ],
    name: Annotated[str, typer.Option("--name", help="Tên model, ví dụ yolov8n-coco")],
    device: Annotated[str, typer.Option("--device", help="Ví dụ cpu, cuda:0")] = "cpu",
) -> None:
    """Hash weights, chạy bài kiểm tra gradient trên ảnh fixture, ghi ModelCard vào store."""
    store = require_store(ctx.obj)
    card = register_model(store, weights, name, load_check_images(), device=device)
    typer.echo(card.model_dump_json(indent=2))
    if not card.supports_gradients:
        typer.echo(
            f"Bài kiểm tra gradient fail: {card.gradient_check.details}. "
            "Attack white-box trên model này sẽ bị skipped.",
            err=True,
        )
