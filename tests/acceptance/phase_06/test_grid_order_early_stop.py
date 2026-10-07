"""validation.md Phase 6, Thứ tự và dừng sớm (`test_grid_order_early_stop.py`). Worker CPU thật.

Tình huống "level 8 làm model sụp" được dựng bằng cách ghi run level 8 là `completed` với metric
sụp trước khi worker nhận experiment (như một worker trước đã chạy xong level đó rồi bị ngắt):
worker mới đọc metric từ bundle và phải tự đánh dấu các level lớn hơn.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from advertest_contracts.enums import RunStatus
from advertest_contracts.models import ProgressReport, RunSkipRequest
from advertest_worker.client import LeaseLost, WorkerClient
from attacks.factory import build_perturbation
from backend.app.db import models as m
from ml_core.runner.grid import coarse_to_fine

from .conftest import World6, grid_attack, ok, post, runs_of

pytestmark = pytest.mark.db

COLLAPSED = {
    "clean": {"map50": 0.6, "map50_95": 0.4},
    "attacked": {"map50": 0.01, "map50_95": 0.005},
    "relative_drop": 0.98,
    "absolute_drop": 0.59,
    "attack_success_rate": None,
    "partial": False,
}


@pytest.fixture
def applied(api: Any) -> Iterator[list[tuple[str, float]]]:
    """(attack, level) mỗi lần worker gọi `Perturbation.apply` (giữ nguyên đối tượng thật)."""
    calls: list[tuple[str, float]] = []
    original = api.perturbation_factory or build_perturbation

    def spy(spec: Any, estimator: Any) -> Any:
        perturbation = original(spec, estimator)
        apply = perturbation.apply

        def recorded(images: Any, targets: Any, level: float, seed: int, mask: Any = None) -> Any:
            calls.append((spec.name, float(level)))
            return apply(images, targets, level, seed, mask)

        perturbation.apply = recorded
        return perturbation

    api.perturbation_factory = spy
    yield calls


def _experiment(api: Any, attacks: list[dict[str, Any]], **changes: Any) -> tuple[Any, Any, str]:
    target = api.target()
    api.profile(target, sec=0.05, batch=3, attacks=sorted({a["_name"] for a in attacks}))
    _, _, client = api.user("engineer")
    clean = [{k: v for k, v in a.items() if k != "_name"} for a in attacks]
    created = ok(post(client, "/experiments", api.body(target, clean, **changes))).json()
    return target, client, created["id"]


def _named(name: str, levels: list[float], **kw: Any) -> dict[str, Any]:
    return {**grid_attack(name, levels, **kw), "_name": name}


def _collapse(owner_engine: Engine, run_id: str) -> None:
    with Session(owner_engine) as session, session.begin():
        row = session.get(m.Run, UUID(run_id))
        assert row is not None
        row.status = RunStatus.COMPLETED
        row.metrics = COLLAPSED
        row.fingerprint = uuid4().hex * 2
        row.manifest_uri = f"s3://artifacts/runs/{run_id}/manifest.json"
        row.images_done = row.images_total


def _by_level(client: Any, experiment_id: str, name: str) -> dict[float, dict[str, Any]]:
    return {
        r["level"]: r for r in runs_of(client, experiment_id) if r["attack_spec"]["name"] == name
    }


def test_order_function() -> None:
    assert coarse_to_fine([2, 4, 8, 16, 32]) == [2, 8, 32, 4, 16]


def test_new_experiment_has_coarse_to_fine_ordinal(api: Any, owner_engine: Engine) -> None:
    _, client, experiment_id = _experiment(api, [_named("fgsm", [2, 4, 8, 16, 32])])
    with Session(owner_engine) as session:
        rows = session.query(m.Run).filter(m.Run.experiment_id == UUID(experiment_id)).all()
    assert [r.level for r in sorted(rows, key=lambda r: r.ordinal)] == [2, 8, 32, 4, 16]
    assert [r["level"] for r in runs_of(client, experiment_id)] == [2, 8, 32, 4, 16]


def test_early_stop_skips_larger_levels_without_running_them(
    api: Any, owner_engine: Engine, applied: list[tuple[str, float]]
) -> None:
    attacks = [_named("fgsm", [2, 4, 8, 16, 32]), _named("pgd_linf", [2, 4])]
    target, client, experiment_id = _experiment(api, attacks)
    fgsm = _by_level(client, experiment_id, "fgsm")
    trigger = fgsm[8.0]["run_id"]
    _collapse(owner_engine, trigger)
    api.work(target, experiment_id)  # worker "mới": chỉ biết level 8 đã sụp qua bundle

    fgsm = _by_level(client, experiment_id, "fgsm")
    for level in (16.0, 32.0):
        run = fgsm[level]
        assert run["status"] == "skipped", run
        assert run["status_reason"]["code"] == "early_stop"
        assert run["status_reason"]["trigger_run_id"] == trigger
    assert fgsm[2.0]["status"] == fgsm[4.0]["status"] == "completed"
    assert ("fgsm", 16.0) not in applied and ("fgsm", 32.0) not in applied
    assert ("fgsm", 2.0) in applied and ("fgsm", 4.0) in applied  # level nhỏ hơn vẫn chạy
    # Dừng sớm của fgsm không ảnh hưởng attack khác.
    pgd = _by_level(client, experiment_id, "pgd_linf")
    assert {r["status"] for r in pgd.values()} == {"completed"}
    assert ("pgd_linf", 2.0) in applied and ("pgd_linf", 4.0) in applied


def test_early_stop_off_runs_every_level(
    api: Any, owner_engine: Engine, applied: list[tuple[str, float]]
) -> None:
    target, client, experiment_id = _experiment(api, [_named("fgsm", [2, 8, 16], early_stop=False)])
    _collapse(owner_engine, _by_level(client, experiment_id, "fgsm")[2.0]["run_id"])
    api.work(target, experiment_id)
    fgsm = _by_level(client, experiment_id, "fgsm")
    assert fgsm[8.0]["status"] == fgsm[16.0]["status"] == "completed"
    assert ("fgsm", 8.0) in applied and ("fgsm", 16.0) in applied


def test_skip_run_not_queued_is_conflict(api: Any, owner_engine: Engine) -> None:
    target, client, experiment_id = _experiment(api, [_named("fgsm", [2, 8, 16])])
    runs = _by_level(client, experiment_id, "fgsm")
    _collapse(owner_engine, runs[2.0]["run_id"])
    _collapse(owner_engine, runs[16.0]["run_id"])  # đã xong, không còn queued
    worker = WorkerClient(api.client(), target.token, sleep=lambda _s: None)
    lease = worker.lease()
    assert lease is not None
    body = RunSkipRequest(
        lease_id=lease.lease_id, code="early_stop",
        trigger_run_id=UUID(runs[2.0]["run_id"]), message="Bỏ qua",
    )  # fmt: skip
    with pytest.raises(LeaseLost) as conflict:
        worker.skip(UUID(runs[16.0]["run_id"]), body)
    assert conflict.value.status_code == 409


def test_training_slice_disjoint(api: Any, world: World6) -> None:
    """`slice create --exclude-slice` cho slice không giao; `GET /slices?disjoint_from=` bỏ slice
    giao."""
    assert not set(world.training_image_ids) & set(world.base.image_ids)
    _, _, client = api.user("engineer")
    listed = client.get(f"/slices?disjoint_from={world.base.slice_id}")
    assert listed.status_code == 200, listed.text
    ids = {s["id"] for s in listed.json()}
    assert world.training_slice_id in ids
    assert world.overlap_slice_id not in ids and world.base.slice_id not in ids


def test_limit_after_first_pass_keeps_smallest_and_largest_level(
    api: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mỗi lần báo tiến độ tính như 100 giây xử lý; giới hạn 350 giây: lượt một (2, 8, 32) xong,
    experiment dừng ở lượt hai."""
    original = WorkerClient.progress

    def slow(self: WorkerClient, run_id: UUID, body: ProgressReport) -> Any:
        return original(self, run_id, body.model_copy(update={"processing_seconds_delta": 100.0}))

    monkeypatch.setattr(WorkerClient, "progress", slow)
    target, client, experiment_id = _experiment(
        api, [_named("fgsm", [2, 4, 8, 16, 32])], limit={"kind": "time", "value": "350"}
    )
    api.work(target, experiment_id)
    fgsm = _by_level(client, experiment_id, "fgsm")
    assert fgsm[2.0]["status"] == fgsm[32.0]["status"] == "completed"
    assert fgsm[2.0]["metrics"] and fgsm[32.0]["metrics"]
    assert fgsm[16.0]["status"] != "completed"
    assert "stopped_limit" in {r["status"] for r in fgsm.values()}
    assert client.get(f"/experiments/{experiment_id}").json()["status"] == "completed"
