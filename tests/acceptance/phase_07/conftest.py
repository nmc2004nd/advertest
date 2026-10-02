"""Fixture cho test nghiệm thu Phase 7 (validation.md Phase 7, Automated Tests).

Test hệ thống (marker `db`, `make test-db`) dùng lại hạ tầng của Phase 5: DB tạm đã migrate và
seed, MinIO, API thật qua TestClient, worker CPU thật `JobRunner`, fixture KITTI 5 ảnh và YOLOv8n.
Tập con 3 ảnh (`subset_size = 3` < 5 ảnh của slice) để có giai đoạn tập con.

Số đo trên slice fixture (CPU, seed 0) dùng để chọn ngưỡng cho từng tình huống: mức sụt tương đối
mAP@0.5 của FGSM ở eps 1/2/4/8/16 là 0.26/0.34/0.57/0.60/0.64 (khoảng 0.8 giây mỗi run); PGD L∞
0.49 ở eps 1, từ 0.97 ở eps 2 trở lên (khoảng 6 giây mỗi run). FGSM với ngưỡng 0.5 trên dải 0-16,
`tol = 2`, 3 level thô (0, 8, 16) đi qua quét thô, chia đôi trên tập con và xác nhận.

`pgd_search` chạy một lần cho cả phiên (PGD tốn thời gian nhất): experiment FGSM quét lưới cộng PGD
L∞ tìm ngưỡng của mục đầu tiên trong "Luồng đầu cuối", ghi lại mọi thứ các test cần đọc.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, select, text
from sqlalchemy.orm import Session

from advertest_contracts.models import SearchResult, SearchResultReport, SearchRunCreate
from advertest_worker import job as job_module
from advertest_worker import search as search_module
from advertest_worker.client import WorkerClient
from attacks.registry import get_spec, load_catalog
from backend.app.db import models as m
from ml_core.models.wrapper import UltralyticsDetector

from ._phase05 import load

P5 = load()

# Hạ tầng của Phase 5: DB tạm, MinIO, API, worker thật. Riêng `owner_engine` viết lại (bên dưới).
alembic_config = P5.alembic_config
app_engine = P5.app_engine
cli_env = P5.cli_env
buckets = P5.buckets
world = P5.world
api = P5.api
fresh_fingerprint = P5.fresh_fingerprint
Api = P5.Api
Target = P5.Target
World = P5.World
attack = P5.attack
spec_id = P5.spec_id
post = P5.post
ok = P5.ok
error = P5.error

SUBSET = 3  # < 5 ảnh của slice fixture


@pytest.fixture(scope="session")
def owner_engine(alembic_config: Config) -> Iterator[Engine]:
    """DB sạch rồi `upgrade head`, như Phase 5 nhưng xóa bằng `DROP OWNED BY` thay cho `downgrade
    base`: chạy chung phiên sau Phase 6, `downgrade` của migration 0006 (xóa spec
    `not_applicable`) vướng run Phase 6 trỏ tới các spec đó. Migration không xóa dữ liệu thật khi
    downgrade, nên dựng DB test bằng `DROP OWNED BY` là cách chính thức (Phase 8 task 37, người
    dùng chốt 2026-10-02)."""
    engine = create_engine(P5.env("ADVERTEST_TEST_OWNER_URL"))
    with engine.begin() as conn:
        conn.execute(text("DROP OWNED BY advertest_owner"))
    command.upgrade(alembic_config, "head")
    yield engine
    engine.dispose()


def search_attack(name: str, *, seed: int = 0, **search: Any) -> dict[str, Any]:
    """Attack tìm ngưỡng; mặc định: `relative_drop` 0.2, dải của spec, `tol` = dải / 256,
    `coarse_n` 4, tập con 3 ảnh, `bootstrap_samples` của contract (200)."""
    spec = get_spec(load_catalog(), name=name)
    param = spec.primary_param
    lo, hi = search.pop("lo", param.min), search.pop("hi", param.max)
    body: dict[str, Any] = {
        "threshold_kind": "relative_drop", "threshold": 0.2, "lo": lo, "hi": hi,
        "tol": (hi - lo) / 256, "coarse_n": 4, "subset_size": SUBSET, **search,
    }  # fmt: skip
    return {
        "attack_spec_id": str(spec.id),
        "spec_sha256": spec.spec_sha256,
        "mode": "search",
        "grid": None,
        "search": body,
        "seed": seed,
    }


def name_of(entry: dict[str, Any]) -> str:
    return next(s.name for s in load_catalog() if str(s.id) == entry["attack_spec_id"])


def setup(
    api: Any, attacks: list[dict[str, Any]], *, sec: float = 0.05, **changes: Any
) -> tuple[Any, Any, str]:
    """Máy chạy mới có cost profile cho mọi attack (batch 5: mỗi run một batch), engineer tạo
    experiment. Trả (target, client của engineer, experiment id)."""
    target = api.target()
    api.profile(target, sec=sec, batch=5, attacks=sorted({name_of(a) for a in attacks}))
    _, _, client = api.user("engineer")
    created = ok(post(client, "/experiments", api.body(target, attacks, **changes))).json()
    return target, client, created["id"]


def runs_of(client: Any, experiment_id: str) -> list[dict[str, Any]]:
    response = client.get(f"/experiments/{experiment_id}/runs")
    assert response.status_code == 200, response.text
    runs: list[dict[str, Any]] = response.json()
    return runs


def detail_of(client: Any, experiment_id: str) -> dict[str, Any]:
    response = client.get(f"/experiments/{experiment_id}")
    assert response.status_code == 200, response.text
    detail: dict[str, Any] = response.json()
    return detail


def result_of(detail: dict[str, Any], name: str) -> SearchResult:
    wanted = str(get_spec(load_catalog(), name=name).id)
    (found,) = [r for r in detail.get("search_results", []) if r["attack_spec_id"] == wanted]
    return SearchResult.model_validate(found)


def ordinals(engine: Engine, experiment_id: str) -> dict[str, int]:
    with Session(engine) as session:
        rows = session.execute(
            select(m.Run.id, m.Run.ordinal).where(m.Run.experiment_id == UUID(experiment_id))
        ).all()
    return {str(run_id): ordinal for run_id, ordinal in rows}


# ---------------------------------------------------------------- ghi lại hoạt động của worker


@dataclass
class Recorder:
    """Ghi lại (gửi thật) kết quả tìm ngưỡng, run động worker tạo, `Perturbation.apply`, số lần
    model chạy trong và ngoài bootstrap. `session` tăng mỗi khi test dựng worker mới."""

    reports: list[tuple[int, SearchResult]] = field(default_factory=list)
    lease_ids: list[UUID] = field(default_factory=list)
    created: list[tuple[int, SearchRunCreate]] = field(default_factory=list)
    applied: list[tuple[str, float]] = field(default_factory=list)
    model_calls: int = 0
    bootstrap_model_calls: int = 0
    session: int = 1
    on_report: Callable[[SearchResult], None] | None = None

    def interim(self, name: str | None = None) -> list[SearchResult]:
        return [r for _, r in self.reports if r.status is None and _is(r, name)]

    def final(self, name: str | None = None) -> list[SearchResult]:
        return [r for _, r in self.reports if r.status is not None and _is(r, name)]


def _is(result: SearchResult, name: str | None) -> bool:
    return name is None or result.attack_spec_id == get_spec(load_catalog(), name=name).id


def install(mp: pytest.MonkeyPatch, rec: Recorder) -> None:
    report, create = WorkerClient.search_result, WorkerClient.create_search_run

    def spy_report(self: WorkerClient, experiment_id: UUID, body: SearchResultReport) -> None:
        report(self, experiment_id, body)
        rec.reports.append((rec.session, body.result))
        rec.lease_ids.append(body.lease_id)
        if rec.on_report is not None:
            rec.on_report(body.result)

    def spy_create(self: WorkerClient, experiment_id: UUID, body: SearchRunCreate) -> Any:
        rec.created.append((rec.session, body))
        return create(self, experiment_id, body)

    original_build = job_module.build_perturbation

    def spy_build(spec: Any, estimator: Any) -> Any:
        perturbation = original_build(spec, estimator)
        apply = perturbation.apply

        def recorded(images: Any, targets: Any, level: float, seed: int, mask: Any = None) -> Any:
            rec.applied.append((spec.name, float(level)))
            return apply(images, targets, level, seed, mask)

        perturbation.apply = recorded
        return perturbation

    forward = UltralyticsDetector.forward

    def counted(self: UltralyticsDetector, *args: Any, **kwargs: Any) -> Any:
        rec.model_calls += 1
        return forward(self, *args, **kwargs)

    bootstrap = search_module.SearchDriver._bootstrap

    def watched(self: Any, progress: Any) -> Any:
        before = rec.model_calls
        try:
            return bootstrap(self, progress)
        finally:
            rec.bootstrap_model_calls += rec.model_calls - before

    mp.setattr(WorkerClient, "search_result", spy_report)
    mp.setattr(WorkerClient, "create_search_run", spy_create)
    mp.setattr(job_module, "build_perturbation", spy_build)
    mp.setattr(UltralyticsDetector, "forward", counted)
    mp.setattr(search_module.SearchDriver, "_bootstrap", watched)


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    rec = Recorder()
    install(monkeypatch, rec)
    return rec


class Crash(Exception):
    """Worker chết giữa chừng (như `kill -9`): lease còn đó, hết hạn sau 60 giây."""


# ---------------------------------------------------------------- PGD L∞ tìm ngưỡng (cả phiên)

PGD_SEARCH: dict[str, Any] = {"lo": 0, "hi": 16, "tol": 2}


@dataclass
class PgdSearch:
    experiment_id: str
    detail: dict[str, Any]
    runs: list[dict[str, Any]]
    ordinals: dict[str, int]
    recorder: Recorder
    polled_points: list[int]  # points_used của PGD đọc qua API sau mỗi batch
    max_points: int


@pytest.fixture(scope="session")
def pgd_search(
    app_engine: Engine,
    buckets: Any,
    cli_env: dict[str, str],
    world: Any,
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[PgdSearch]:
    """Experiment FGSM quét lưới eps 2, 4 cộng PGD L∞ tìm ngưỡng (`relative_drop` 0.2, dải
    0-16, `tol = 2`, `subset_size = 3`, bootstrap 200 mẫu), chạy xong bằng worker thật."""
    session_api = Api(app_engine, buckets, cli_env, world, tmp_path_factory.mktemp("phase07-pgd"))
    rec = Recorder()
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("GIT_COMMIT", uuid.uuid4().hex + uuid.uuid4().hex[:8])
        mp.delenv("DOCKER_IMAGE_DIGEST", raising=False)
        mp.setenv("TRUSTED_PROXIES", "testclient")
        install(mp, rec)
        attacks = [attack("fgsm", [2, 4]), search_attack("pgd_linf", **PGD_SEARCH)]
        target, client, experiment_id = setup(session_api, attacks)
        estimate = ok(
            post(client, "/experiments/estimate", session_api.body(target, attacks))
        ).json()
        (row,) = estimate["searches"]
        polled: list[int] = []

        def poll(_run_id: UUID, _ids: Any) -> None:
            detail = detail_of(client, experiment_id)
            pgd = [r for r in detail.get("search_results", []) if r["stage"] != "done"]
            polled.extend(r["points_used"] for r in pgd)

        session_api.work(target, experiment_id, on_batch=poll)
        yield PgdSearch(
            experiment_id=experiment_id,
            detail=detail_of(client, experiment_id),
            runs=runs_of(client, experiment_id),
            ordinals=ordinals(app_engine, experiment_id),
            recorder=rec,
            polled_points=polled,
            max_points=row["max_points"],
        )


@pytest.fixture
def bootstrap_model_calls(pgd_search: PgdSearch) -> tuple[int, int]:
    """(số lần model chạy ngoài bootstrap, trong bootstrap) của lần tìm ngưỡng PGD."""
    rec = pgd_search.recorder
    assert rec.final("pgd_linf"), "PGD chưa có kết quả cuối"
    return rec.model_calls - rec.bootstrap_model_calls, rec.bootstrap_model_calls
