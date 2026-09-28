"""Lệnh CLI của ml-data. Group 2 thêm `dataset import-kitti`, `mapping create`, `slice create`.

File này có 3 `typer.Typer` vì mỗi nhóm lệnh là một sub-app của `advertest`
(ngoại lệ của quy tắc "mỗi file một Typer" trong plan.md Phase 1).
Lấy store trong lệnh bằng `ml_core.store.require_store(ctx.obj)`.
"""

from __future__ import annotations

import typer

dataset_app = typer.Typer(help="Import và quản lý dataset version.", no_args_is_help=True)
slice_app = typer.Typer(help="Tạo và xem slice.", no_args_is_help=True)
mapping_app = typer.Typer(help="Tạo và xem class mapping.", no_args_is_help=True)
