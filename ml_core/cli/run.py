"""`advertest run --config <yaml> [--force]` và `advertest run show <fingerprint>`.

stdout là JSON (mảng `RunResult`, hoặc `RunResult` với `run show`) để máy đọc được; tiến độ, cảnh
báo và bảng tóm tắt in ra stderr.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, NoReturn

import typer
from pydantic import ValidationError

from advertest_contracts.models import RunResult
from attacks.registry import UnknownAttack
from ml_core.runner.config import load_config
from ml_core.store import ArtifactStore, KeyNotFoundError, require_store

if TYPE_CHECKING:
    from ml_core.runner.run import RunOutcome

# `ml_core.runner.run` được import trong từng lệnh: runner dùng `ml_core.cli.cache` và
# `ml_core.cli.evaluate`, nên import ở đầu file tạo vòng runner.run → ml_core.cli → cli.run.

run_app = typer.Typer(
    help="Chạy attack theo cấu hình (quét lưới), xem kết quả theo fingerprint.",
    invoke_without_command=True,
)


def _err(message: str) -> None:
    typer.echo(message, err=True)


def _fail(exc: BaseException) -> NoReturn:
    message = exc.args[0] if exc.args else str(exc)
    _err(f"Lỗi: {message}")
    raise typer.Exit(code=1) from exc


def _fmt(value: float | None, digits: int = 4) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def summary_table(outcomes: list[RunOutcome]) -> str:
    header = ("attack", "level", "mAP sạch", "mAP tấn công", "relative drop", "ASR", "trạng thái")
    rows = [header]
    for outcome in outcomes:
        result = outcome.result
        metrics = result.metrics
        status = result.status.value
        if result.status_reason is not None:
            status += f" ({result.status_reason.code})"
        rows.append(
            (
                outcome.spec_name,
                f"{result.level:g}",
                _fmt(metrics.clean.map50 if metrics else None),
                _fmt(metrics.attacked.map50 if metrics else None),
                _fmt(metrics.relative_drop if metrics else None, 3),
                _fmt(metrics.attack_success_rate if metrics else None, 3),
                status,
            )
        )
    widths = [max(len(row[i]) for row in rows) for i in range(len(header))]
    lines = ["  ".join(cell.ljust(w) for cell, w in zip(row, widths, strict=True)) for row in rows]
    lines.insert(1, "  ".join("-" * w for w in widths))
    return "\n".join(lines)


@run_app.callback()
def run(
    ctx: typer.Context,
    config: Annotated[
        Path | None, typer.Option("--config", help="File YAML LocalRunConfig", exists=True)
    ] = None,
    force: Annotated[
        bool, typer.Option("--force", help="Bỏ qua cache, chạy lại vào reruns/<run_id>/")
    ] = False,
) -> None:
    """Chạy mọi (attack, level) trong cấu hình, tuần tự."""
    if ctx.invoked_subcommand is not None:
        return
    if config is None:
        _err("Cần --config <yaml> (hoặc lệnh con `show`)")
        raise typer.Exit(code=2)
    from ml_core.runner.run import Runner

    store = require_store(ctx.obj)
    try:
        runner = Runner(store, load_config(config), force=force, progress=_err)
        if runner.git.dirty:
            _err(
                "Cảnh báo: working tree có thay đổi chưa commit (ngoài .ai-log/); "
                "git_dirty = true trong fingerprint"
            )
        report = runner.run()
    except (KeyNotFoundError, FileNotFoundError, ValueError, ValidationError, UnknownAttack) as exc:
        _fail(exc)
    _err("")
    _err(
        f"Experiment {report.experiment_id}: mAP@0.5 sạch = {report.clean.map50:.4f}, "
        f"mAP@0.5:0.95 sạch = {report.clean.map50_95:.4f}"
    )
    _err(summary_table(report.outcomes))
    for outcome in report.outcomes:
        if outcome.prefix is not None:
            _err(f"{outcome.spec_name} {outcome.result.level:g}: {outcome.prefix}")
    typer.echo(json.dumps([o.result.model_dump(mode="json") for o in report.outcomes], indent=2))


def _location(store: ArtifactStore, key: str) -> str:
    root = getattr(store, "root", None)
    return str(Path(root) / key) if root is not None else key


@run_app.command("show")
def show(
    ctx: typer.Context,
    fingerprint: Annotated[str, typer.Argument(help="Fingerprint của run (sha256)")],
) -> None:
    """In RunResult của fingerprint và đường dẫn artifact (kể cả các lần --force và run lỗi)."""
    from ml_core.runner.run import result_key, run_prefix

    store = require_store(ctx.obj)
    prefix = run_prefix(fingerprint)
    try:
        keys = store.list(f"{prefix}/")
    except ValueError as exc:
        _fail(exc)
    results = [k for k in keys if k.endswith("/result.json")]
    if not results:
        _fail(KeyNotFoundError(f"Không có run nào với fingerprint {fingerprint}"))
    main = result_key(prefix)
    if store.exists(main):
        typer.echo(RunResult.model_validate_json(store.get(main)).model_dump_json(indent=2))
    else:
        _err("Chưa có kết quả completed ở thư mục chính")
    _err("Artifact:")
    for key in keys:
        _err(f"  {_location(store, key)}")
    others = [k for k in results if k != main]
    if others:
        _err("Các lần chạy khác (reruns/, attempts/):")
        for key in others:
            other = RunResult.model_validate_json(store.get(key))
            _err(f"  {other.status.value}: {_location(store, key)}")
