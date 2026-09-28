"""Lệnh CLI của ml-model. Group 3 thêm `model register`.

Lấy store trong lệnh bằng `ml_core.store.require_store(ctx.obj)`.
"""

from __future__ import annotations

import typer

app = typer.Typer(help="Đăng ký và xem model.", no_args_is_help=True)
