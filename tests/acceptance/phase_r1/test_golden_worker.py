"""Golden Phase R1, đường worker (`JobRunner` qua API thật), marker `db` (`make test-db`).

World của Phase 6: slice đánh giá 3 ảnh (seed 6), slice huấn luyện 2 ảnh, spec patch `max_iter` 4.
Cost profile cố định batch 4 (mỗi run một batch), không calibration.
- Experiment A (quét lưới): 9 spec của catalog x 2 level như đường CLI, cộng patch x 2 level (train
  patch, `_patch_perturbation`), early stop mặc định.
- Experiment B (tìm ngưỡng): PGD L∞ `relative_drop` 0.2, dải 0-16, `tol` 2, tập con 2 ảnh,
  bootstrap 50 mẫu (`RunPlanner` và hook tìm ngưỡng).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from attacks.registry import get_spec, load_catalog
from backend.app.db import models as m

from .conftest import P5, P6
from .golden import (
    COMMIT,
    GOLDEN_DIR,
    LEVELS,
    PATCH_LEVELS,
    case_entry,
    check_or_record,
    run_entry,
    run_key,
    snapshot,
)

pytestmark = pytest.mark.db

GOLDEN = GOLDEN_DIR / "phase_r1_worker.json"
SEARCH = {
    "threshold_kind": "relative_drop", "threshold": 0.2, "lo": 0, "hi": 16, "tol": 2,
    "coarse_n": 4, "subset_size": 2, "bootstrap_samples": 50,
}  # fmt: skip
ARTIFACTS = "s3://artifacts/"


def _spec_id(name: str) -> UUID:
    return get_spec(load_catalog(), name=name).id


def _run(api: Any, attacks: list[dict[str, Any]], profiles: dict[UUID, float],
         per_iteration: dict[UUID, float] | None = None) -> str:  # fmt: skip
    target = api.target()
    P6.profile(api, target, profiles, batch=4, sec_per_image_iteration=per_iteration)
    _, _, client = api.user("engineer")
    created = P5.ok(P5.post(client, "/experiments", api.body(target, attacks))).json()
    api.work(target, created["id"])
    return str(created["id"])


def _case(row: m.FailureCase) -> dict[str, Any]:
    return {
        "image_id": row.image_id,
        "severity_score": row.severity_score,
        "lost_objects": row.lost_objects,
        "new_false_positives": row.new_false_positives,
    }


def _runs(engine: Engine, buckets: Any, experiment_id: str, label: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    with Session(engine) as session:
        rows = session.execute(
            select(m.Run, m.AttackSpecRow.name)
            .join(m.AttackSpecRow, m.AttackSpecRow.id == m.Run.attack_spec_id)
            .where(m.Run.experiment_id == UUID(experiment_id))
        ).all()
        for run, name in rows:
            inputs = None
            if run.manifest_uri is not None:
                key = run.manifest_uri.removeprefix(ARTIFACTS)
                manifest = json.loads(buckets.artifacts.get(key))
                inputs = manifest["fingerprint_inputs"]
            cases = session.scalars(
                select(m.FailureCase).where(m.FailureCase.run_id == run.id)
            ).all()
            name_key = f"{label}:" + run_key(name, run.level, run.scope, run.search_order)
            assert name_key not in out, f"trùng khóa run {name_key}"
            out[name_key] = run_entry(
                status=str(run.status.value),
                reason=(run.status_reason or {}).get("code"),
                fingerprint=run.fingerprint,
                fingerprint_inputs=inputs,
                metrics=run.metrics,
                cases=[case_entry(_case(c), c.rank) for c in cases],
            )
    return out


def _searches(engine: Engine, experiment_id: str) -> dict[str, Any]:
    with Session(engine) as session:
        rows = session.execute(
            select(m.SearchResultRow.result, m.AttackSpecRow.name)
            .join(m.AttackSpecRow, m.AttackSpecRow.id == m.SearchResultRow.attack_spec_id)
            .where(m.SearchResultRow.experiment_id == UUID(experiment_id))
        ).all()
    drop = {"experiment_id", "attack_spec_id"}
    out: dict[str, Any] = {}
    for result, name in rows:
        body = {k: v for k, v in result.items() if k not in drop}
        # run_id là uuid4 ngẫu nhiên: chỉ giữ việc điểm có run hay không (synthetic).
        body["trajectory"] = [
            {**{k: v for k, v in p.items() if k != "run_id"}, "has_run": p["run_id"] is not None}
            for p in body["trajectory"]
        ]
        out[name] = body
    return out


@pytest.mark.usefixtures("pinned_threads")
def test_worker_runner_matches_golden(
    app_engine: Engine, buckets: Any, cli_env: dict[str, str], world: Any, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    monkeypatch.setenv("GIT_COMMIT", COMMIT)
    monkeypatch.delenv("DOCKER_IMAGE_DIGEST", raising=False)
    monkeypatch.delenv("DEV_ALLOW_UNBLURRED", raising=False)
    monkeypatch.setenv("TRUSTED_PROXIES", "testclient")
    api = P5.Api(app_engine, buckets, cli_env, world.base, tmp_path)

    grid = [P5.attack(name, levels) for name, levels in LEVELS.items()]
    grid.append(P6.patch_attack(world, PATCH_LEVELS))
    profiles = {_spec_id(name): 0.05 for name in LEVELS} | {world.patch.id: 0.05}
    grid_id = _run(api, grid, profiles, {world.patch.id: 0.2})

    spec = get_spec(load_catalog(), name="pgd_linf")
    search = {
        "attack_spec_id": str(spec.id), "spec_sha256": spec.spec_sha256, "mode": "search",
        "grid": None, "search": SEARCH, "seed": 0,
    }  # fmt: skip
    search_id = _run(api, [search], {spec.id: 0.05})

    runs = _runs(app_engine, buckets, grid_id, "grid") | _runs(
        app_engine, buckets, search_id, "search"
    )
    check_or_record(snapshot(runs, searches=_searches(app_engine, search_id)), GOLDEN)
