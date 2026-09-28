"""Lệnh CLI của ml-data: `dataset import-kitti`, `mapping create`, `slice create`.

File này có 3 `typer.Typer` vì mỗi nhóm lệnh là một sub-app của `advertest`
(ngoại lệ của quy tắc "mỗi file một Typer" trong plan.md Phase 1).
Lấy store trong lệnh bằng `ml_core.store.require_store(ctx.obj)`.
Mỗi lệnh in kết quả dạng JSON ra stdout; lỗi dữ liệu in ra stderr và thoát mã 1.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, TypeVar
from uuid import UUID

import typer

from advertest_contracts.ids import content_id
from ml_core.data.dataset import load_manifest, save_dataset
from ml_core.data.kitti import KittiLabelError, import_kitti
from ml_core.data.mapping import build_mapping, save_mapping
from ml_core.data.slice import DEFAULT_SIZE, create_slice, preset_filter, save_slice
from ml_core.models.register import load_card
from ml_core.store import KeyNotFoundError, require_store, resolve_id

dataset_app = typer.Typer(help="Import và quản lý dataset version.", no_args_is_help=True)
slice_app = typer.Typer(help="Tạo và xem slice.", no_args_is_help=True)
mapping_app = typer.Typer(help="Tạo và xem class mapping.", no_args_is_help=True)

T = TypeVar("T")

DatasetOption = Annotated[
    str, typer.Option("--dataset", help="dataset_version_sha256 (in ra khi import)")
]
PresetOption = Annotated[str, typer.Option("--preset", help="Preset mapping, ví dụ kitti-coco")]


def _run(action: Callable[[], T]) -> T:
    """Chạy `action`; lỗi dữ liệu thành thông báo gọn trên stderr, thoát mã 1."""
    try:
        return action()
    except (KeyNotFoundError, FileNotFoundError, KittiLabelError, ValueError) as exc:
        message = exc.args[0] if exc.args else str(exc)
        typer.echo(f"Lỗi: {message}", err=True)
        raise typer.Exit(code=1) from exc


@dataset_app.command("import-kitti")
def import_kitti_command(
    ctx: typer.Context,
    root: Annotated[
        Path,
        typer.Option("--root", exists=True, file_okay=False, help="Thư mục có image_2/, label_2/"),
    ],
    split: Annotated[str, typer.Option("--split", help="Tên split, ghi vào manifest")] = "training",
) -> None:
    """Tạo manifest từ KITTI, lưu vào store, in `dataset_version_sha256`."""
    store = require_store(ctx.obj)
    manifest = _run(lambda: import_kitti(root, split))
    sha = save_dataset(store, manifest, root)
    summary = {
        "dataset_version_sha256": sha,
        "id": str(content_id(sha)),
        "num_images": len(manifest.images),
        "num_annotations": len(manifest.annotations),
        "num_ignore_regions": len(manifest.ignore_regions),
    }
    typer.echo(json.dumps(summary, indent=2))


@mapping_app.command("create")
def mapping_create(
    ctx: typer.Context,
    dataset: DatasetOption,
    model: Annotated[UUID, typer.Option("--model", help="id của model đã đăng ký")],
    preset: PresetOption = "kitti-coco",
) -> None:
    """Tạo class mapping cho dataset và model, lưu vào store, in `ClassMapping`."""
    store = require_store(ctx.obj)
    _run(lambda: load_manifest(store, dataset))
    card = _run(lambda: load_card(store, resolve_id(store, "model", model)))
    mapping = _run(lambda: build_mapping(dataset, card, preset))
    save_mapping(store, mapping)
    typer.echo(mapping.model_dump_json(indent=2))


@slice_app.command("create")
def slice_create(
    ctx: typer.Context,
    dataset: DatasetOption,
    size: Annotated[int, typer.Option("--size", min=1, help="Số ảnh")] = DEFAULT_SIZE,
    seed: Annotated[int, typer.Option("--seed", min=0)] = 42,
    preset: PresetOption = "kitti-coco",
) -> None:
    """Tạo slice cố định (không cần model hay mapping), lưu vào store, in `SliceSpec`."""
    store = require_store(ctx.obj)
    manifest = _run(lambda: load_manifest(store, dataset))
    spec = _run(lambda: create_slice(manifest, size, seed, preset_filter(preset)))
    save_slice(store, spec)
    typer.echo(spec.model_dump_json(indent=2))
