"""Lệnh CLI của ml-model: `advertest model register`, `advertest model export-safetensors`.

Lấy store trong lệnh bằng `ml_core.store.require_store(ctx.obj)`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ml_core.models.register import load_check_images, register_model
from ml_core.models.ultralytics_safetensors import export_safetensors
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
    if card.name != name:
        typer.echo(
            f"Cảnh báo: weights này đã được đăng ký với tên {card.name!r}; "
            f"tên {name!r} không được dùng.",
            err=True,
        )
    if not card.supports_gradients:
        typer.echo(
            f"Bài kiểm tra gradient fail: {card.gradient_check.details}. "
            "Attack white-box trên model này sẽ bị skipped.",
            err=True,
        )


@app.command("export-safetensors")
def export_safetensors_cmd(
    checkpoint: Annotated[
        Path, typer.Argument(exists=True, dir_okay=False, help="Checkpoint Ultralytics (.pt)")
    ],
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Mặc định cạnh file .pt")
    ] = None,
    architecture: Annotated[
        str | None,
        typer.Option("--architecture", help="Ví dụ yolo11n; mặc định đọc từ checkpoint"),
    ] = None,
) -> None:
    """Đổi `.pt` của Ultralytics sang `.safetensors` để đăng ký qua web (framework ultralytics,
    có gradient). Chỉ chạy với checkpoint bạn tin: `.pt` là pickle."""
    target = output or checkpoint.with_suffix(".safetensors")
    arch, names = export_safetensors(checkpoint, target, architecture)
    typer.echo(f"{target} — kiến trúc {arch}, {len(names)} class")
