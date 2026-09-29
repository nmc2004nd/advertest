"""CLI quản trị `advertest-admin` (validation.md Phase 3: kiểm toán; requirements.md, CLI quản
trị). Postgres và MinIO thật (`make test-db`)."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
import yaml
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session
from typer.testing import CliRunner, Result

from advertest_contracts.enums import Role
from backend.admin_cli import cli
from backend.app.db import models as m
from backend.app.storage import Buckets

from .conftest import _url, make_user
from .local_store_factory import LocalData, build_local_store
from .test_worker_services import World, _config, world

pytestmark = pytest.mark.db
__all__ = ["world"]


@pytest.fixture
def env() -> dict[str, str]:
    return {
        "DATABASE_URL": _url("ADVERTEST_TEST_APP_URL"),
        "MINIO_ENDPOINT": _url("ADVERTEST_TEST_MINIO_ENDPOINT"),
        "MINIO_ACCESS_KEY": _url("ADVERTEST_TEST_MINIO_ACCESS_KEY"),
        "MINIO_SECRET_KEY": _url("ADVERTEST_TEST_MINIO_SECRET_KEY"),
    }


def _invoke(env: dict[str, str], *args: str) -> Result:
    return CliRunner().invoke(cli.app, list(args), env=env)


def _users(app_engine: Engine) -> tuple[str, str]:
    with Session(app_engine) as session, session.begin():
        return make_user(session).email, make_user(session, role=Role.ENGINEER).email


def _actions(app_engine: Engine, email: str) -> list[str]:
    with Session(app_engine) as session:
        return list(
            session.scalars(
                select(m.AuditLog.action)
                .join(m.User, m.User.id == m.AuditLog.actor_id)
                .where(m.User.email == email)
                .order_by(m.AuditLog.created_at)
            )
        )


def test_compute_target_commands_and_audit(app_engine: Engine, env: dict[str, str]) -> None:
    admin, engineer = _users(app_engine)
    name = f"t-{uuid.uuid4().hex[:8]}"
    created = _invoke(env, "compute-target", "create", "--name", name, "--as", admin)
    assert created.exit_code == 0, created.output
    token = created.output.strip().splitlines()[-1]
    with Session(app_engine) as session:
        target = session.scalars(select(m.ComputeTarget).where(m.ComputeTarget.name == name)).one()
        assert target.token_hash is not None and token not in target.token_hash
    rotated = _invoke(env, "compute-target", "rotate-token", name, "--as", admin)
    assert rotated.exit_code == 0 and rotated.output.strip().splitlines()[-1] != token
    listed = _invoke(env, "compute-target", "list")
    assert name in listed.output and "có token" in listed.output
    assert _actions(app_engine, admin) == ["compute_target.create", "compute_target.rotate_token"]

    denied = _invoke(env, "compute-target", "create", "--name", f"{name}-x", "--as", engineer)
    assert denied.exit_code == 1 and "admin" in denied.output
    unknown = _invoke(env, "compute-target", "rotate-token", name, "--as", "khong-co@x.test")
    assert unknown.exit_code == 1
    rented = _invoke(env, "compute-target", "create", "--name", f"{name}-r", "--kind", "rented",
                     "--as", admin)  # fmt: skip
    assert rented.exit_code == 1


def test_compute_target_set_limits(app_engine: Engine, env: dict[str, str]) -> None:
    """Phase 5: admin đổi giới hạn thời gian qua `compute-target set-limits`."""
    admin, engineer = _users(app_engine)
    name = f"t-{uuid.uuid4().hex[:8]}"
    created = _invoke(env, "compute-target", "create", "--name", name, "--max-time-limit",
                      "14400", "--as", admin)  # fmt: skip
    assert created.exit_code == 0, created.output
    changed = _invoke(env, "compute-target", "set-limits", name, "--default", "3600", "--max",
                      "36000", "--as", admin)  # fmt: skip
    assert changed.exit_code == 0, changed.output
    with Session(app_engine) as session:
        target = session.scalars(select(m.ComputeTarget).where(m.ComputeTarget.name == name)).one()
        assert (target.default_time_limit_s, target.max_time_limit_s) == (3600, 36000)
    assert "tối đa 36000s" in _invoke(env, "compute-target", "list").output
    assert _actions(app_engine, admin)[-1] == "compute_target.update_limits"

    too_big = _invoke(env, "compute-target", "set-limits", name, "--default", "40000", "--as",
                      admin)  # fmt: skip
    assert too_big.exit_code == 1
    nothing = _invoke(env, "compute-target", "set-limits", name, "--as", admin)
    assert nothing.exit_code == 1
    denied = _invoke(env, "compute-target", "set-limits", name, "--max", "100", "--as", engineer)
    assert denied.exit_code == 1 and "admin" in denied.output


def test_import_local_requires_admin(
    app_engine: Engine, env: dict[str, str], buckets: Buckets, tmp_path: Path
) -> None:
    admin, engineer = _users(app_engine)
    local: LocalData = build_local_store(tmp_path, image_size=(162, 40))
    store = str(tmp_path / "store")
    denied = _invoke(env, "import-local", "--store", store, "--as", engineer)
    assert denied.exit_code == 1
    done = _invoke(env, "import-local", "--store", store, "--as", admin)
    assert done.exit_code == 0, done.output
    assert "slice: 1" in done.output and "ảnh mới upload: 2" in done.output
    assert buckets.datasets.exists(f"slices/{local.slice.slice_sha256}.json")
    assert _actions(app_engine, admin) == ["registry.import_local"]


def test_submit_show_list_cancel(
    app_engine: Engine, env: dict[str, str], world: World, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    admin, engineer = _users(app_engine)
    name = f"t-{uuid.uuid4().hex[:8]}"
    assert _invoke(env, "compute-target", "create", "--name", name, "--as", admin).exit_code == 0
    config = tmp_path / "config.yaml"
    config.write_text(yaml.safe_dump(_config(world).model_dump(mode="json")))

    denied = _invoke(env, "submit", "--config", str(config), "--target", name, "--as", engineer)
    assert denied.exit_code == 1
    submitted = _invoke(env, "submit", "--config", str(config), "--target", name,
                        "--time-limit", "900", "--as", admin)  # fmt: skip
    assert submitted.exit_code == 0, submitted.output
    assert "3 run" in submitted.output and "900 giây" in submitted.output
    assert "chưa có ước lượng" in submitted.output
    experiment_id = submitted.output.split()[1].rstrip(":")

    assert experiment_id in _invoke(env, "experiment", "list").output
    shown = _invoke(env, "experiment", "show", experiment_id)
    assert shown.exit_code == 0 and "[queued]" in shown.output
    assert shown.output.count("0/2 ảnh") == 3 and "fgsm 4" in shown.output

    cancelled = _invoke(env, "experiment", "cancel", experiment_id, "--as", admin)
    assert cancelled.exit_code == 0 and "cancelled" in cancelled.output
    again = _invoke(env, "experiment", "cancel", experiment_id, "--as", admin)
    assert again.exit_code == 1

    sleeps: list[float] = []
    monkeypatch.setattr(cli, "_sleep", sleeps.append)
    watched = _invoke(env, "experiment", "show", experiment_id, "--watch")
    assert watched.exit_code == 0 and "[cancelled]" in watched.output
    assert sleeps == []  # experiment đã kết thúc: không lặp
    assert _actions(app_engine, admin)[-2:] == ["experiment.submit", "experiment.cancel"]
    missing = _invoke(env, "experiment", "show", str(uuid.uuid4()))
    assert missing.exit_code == 1
