from pathlib import Path
from uuid import UUID

import pytest
import typer
from typer.testing import CliRunner

from ml_core.cli import app
from ml_core.store import LocalStore, require_store

runner = CliRunner()
ZERO = str(UUID(int=0))


def test_help_lists_all_command_groups() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for name in ("model", "dataset", "slice", "mapping", "eval", "viz"):
        assert name in result.output


@pytest.mark.parametrize("group", ["model", "dataset", "slice", "mapping"])
def test_sub_app_help(group: str) -> None:
    result = runner.invoke(app, [group, "--help"])
    assert result.exit_code == 0


@pytest.mark.parametrize(
    "args",
    [
        ["eval", "--model", ZERO, "--slice", ZERO, "--mapping", ZERO, "--out", "x.json"],
        ["viz", "--model", ZERO, "--slice", ZERO, "--mapping", ZERO, "--out", "out"],
    ],
)
def test_eval_viz_not_implemented_yet(args: list[str]) -> None:
    result = runner.invoke(app, args)
    assert result.exit_code == 1
    assert "Group 5" in result.output


def test_eval_rejects_non_uuid() -> None:
    result = runner.invoke(
        app, ["eval", "--model", "abc", "--slice", ZERO, "--mapping", ZERO, "--out", "x"]
    )
    assert result.exit_code == 2


def test_store_dir_option_sets_ctx_obj(tmp_path: Path) -> None:
    probe = typer.Typer()
    seen: list[object] = []

    @probe.command("probe")
    def _probe(ctx: typer.Context) -> None:
        seen.append(require_store(ctx.obj))

    app.add_typer(probe, name="probe-test")
    try:
        result = runner.invoke(app, ["--store-dir", str(tmp_path), "probe-test", "probe"])
    finally:
        app.registered_groups.pop()
    assert result.exit_code == 0, result.output
    assert isinstance(seen[0], LocalStore)
    assert seen[0].root == tmp_path


def test_require_store_rejects_missing_obj() -> None:
    with pytest.raises(RuntimeError):
        require_store(None)
