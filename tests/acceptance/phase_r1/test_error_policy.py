"""Chính sách lỗi và provenance qua seam, worker thật, marker `db` (validation.md Phase R1,
`### Chính sách lỗi`).

Test chỉ thay thế qua seam của `JobRunner` (`perturbation_factory`, `provenance`, truyền qua
`P5.Api`), không patch tên ở cấp module.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from advertest_contracts.enums import RunStatus
from advertest_contracts.models import LibVersions
from attacks.factory import build_perturbation
from attacks.registry import get_spec, load_catalog
from backend.app.db import models as m
from ml_core.models.register import lib_versions
from ml_core.runner.env import GitState

from .conftest import P5, P6

pytestmark = pytest.mark.db

ARTIFACTS = "s3://artifacts/"


@pytest.fixture
def api(
    app_engine: Engine, buckets: Any, cli_env: dict[str, str], world: Any, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Any:  # fmt: skip
    # Commit riêng mỗi test: không trúng cache của run khác trong cùng phiên `make test-db`.
    monkeypatch.setenv("GIT_COMMIT", uuid.uuid4().hex + uuid.uuid4().hex[:8])
    monkeypatch.delenv("DOCKER_IMAGE_DIGEST", raising=False)
    monkeypatch.setenv("TRUSTED_PROXIES", "testclient")
    return P5.Api(app_engine, buckets, cli_env, world.base, tmp_path)


def _run_experiment(api: Any, attacks: dict[str, list[float]]) -> str:
    target = api.target()
    profiles = {get_spec(load_catalog(), name=name).id: 0.05 for name in attacks}
    P6.profile(api, target, profiles, batch=4)
    _, _, client = api.user("engineer")
    body = api.body(target, [P5.attack(name, levels) for name, levels in attacks.items()])
    created = P5.ok(P5.post(client, "/experiments", body)).json()
    api.work(target, created["id"])
    return str(created["id"])


def _runs(engine: Engine, experiment_id: str) -> list[tuple[str, m.Run]]:
    with Session(engine, expire_on_commit=False) as session:
        rows = session.execute(
            select(m.AttackSpecRow.name, m.Run)
            .join(m.AttackSpecRow, m.AttackSpecRow.id == m.Run.attack_spec_id)
            .where(m.Run.experiment_id == UUID(experiment_id))
        ).all()
        session.expunge_all()
    return [(name, run) for name, run in rows]


def test_builder_error_fails_only_that_run(api: Any, app_engine: Engine) -> None:
    """Builder ném lỗi ở lần dựng thứ hai: run đó `failed` (`error`), run khác `completed`."""
    built: list[str] = []

    def flaky(spec: Any, estimator: Any) -> Any:
        built.append(spec.name)
        if len(built) == 2:
            raise RuntimeError("builder giả: lỗi khi dựng perturbation")
        return build_perturbation(spec, estimator)

    api.perturbation_factory = flaky
    experiment_id = _run_experiment(api, {"fgsm": [4], "fog": [1]})

    assert len(built) >= 2, built
    broken = built[1]
    runs = _runs(app_engine, experiment_id)
    assert {name for name, _ in runs} == {"fgsm", "fog"}
    for name, run in runs:
        if name == broken:
            assert run.status == RunStatus.FAILED, (name, run.status)
            reason = run.status_reason or {}
            assert reason.get("code") == "error" and "builder giả" in reason.get("message", "")
        else:
            assert run.status == RunStatus.COMPLETED, (name, run.status, run.status_reason)


class DirtyProvenance:
    """Provenance giả (không kế thừa cài đặt mặc định): working tree có thay đổi chưa commit."""

    def __init__(self) -> None:
        self.state = GitState(commit=uuid.uuid4().hex + uuid.uuid4().hex[:8], dirty=True)

    def git(self) -> GitState:
        return self.state

    def lib_versions(self) -> LibVersions:
        return lib_versions()

    def docker_image_digest(self) -> str:
        return "none"


def test_fake_provenance_reaches_manifest(api: Any, app_engine: Engine, buckets: Any) -> None:
    """Provenance giả có `dirty = true`: `git_dirty` và `git_commit` trong manifest lấy từ seam."""
    provenance = DirtyProvenance()
    api.provenance = provenance
    experiment_id = _run_experiment(api, {"fog": [1]})

    ((_, run),) = _runs(app_engine, experiment_id)
    assert run.status == RunStatus.COMPLETED and run.manifest_uri is not None
    manifest = json.loads(buckets.artifacts.get(run.manifest_uri.removeprefix(ARTIFACTS)))
    inputs = manifest["fingerprint_inputs"]
    assert inputs["git_dirty"] is True
    assert inputs["git_commit"] == provenance.state.commit
    assert inputs["docker_image_digest"] == "none"
