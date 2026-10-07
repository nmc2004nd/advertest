"""validation.md Phase 7, Luồng đầu cuối (`test_search_e2e_backend.py`): worker CPU thật, fixture
KITTI 5 ảnh, tập con 3 ảnh. Lý do chọn ngưỡng: docstring của `conftest.py`."""

from __future__ import annotations

import time
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest

from advertest_contracts.enums import EvalScope, SearchStage, SearchStatus
from advertest_contracts.models import ProgressReport, RunView, SearchResult
from advertest_worker.client import WorkerClient
from attacks.factory import build_perturbation
from attacks.registry import get_spec, load_catalog

from .conftest import (
    Crash,
    PgdSearch,
    Recorder,
    attack,
    detail_of,
    ok,
    post,
    result_of,
    runs_of,
    search_attack,
    setup,
)

pytestmark = pytest.mark.db

PGD_ID = str(get_spec(load_catalog(), name="pgd_linf").id)
FGSM_ID = str(get_spec(load_catalog(), name="fgsm").id)
# FGSM ngưỡng 0.5 trên 0-16, tol 2, 3 level thô: quét thô 8, 16 → chia đôi 4, 2 trên tập con →
# xác nhận 2, 4 trên toàn slice (số đo trong conftest). Trên tập con 3 ảnh FGSM gần bão hòa từ
# eps 8 nên mức sụt thô có thể giảm nhẹ: kết quả là `found` hoặc `non_monotonic` (đều có điểm gãy).
BROKE = (SearchStatus.FOUND, SearchStatus.NON_MONOTONIC)
FGSM_SEARCH: dict[str, Any] = {"threshold": 0.5, "lo": 0, "hi": 16, "tol": 2, "coarse_n": 3}


def _pgd_runs(pgd: PgdSearch) -> list[dict[str, Any]]:
    return [r for r in pgd.runs if r["attack_spec_id"] == PGD_ID]


# ---------------------------------------------------------------- PGD L∞ (chạy một lần)


def test_pgd_search_completes_within_max_points(pgd_search: PgdSearch) -> None:
    assert pgd_search.detail["status"] == "completed"
    result = result_of(pgd_search.detail, "pgd_linf")
    assert result.status in BROKE, result
    assert result.stage == SearchStage.DONE
    assert result.points_used <= result.max_points == pgd_search.max_points
    assert result.breaking_point == result.bracket[1]
    a, b = result.bracket
    assert b - a <= 2 + 1e-9
    assert result.confidence_interval is not None  # bootstrap 200 mẫu


def test_each_point_has_matching_run(pgd_search: PgdSearch) -> None:
    result = result_of(pgd_search.detail, "pgd_linf")
    runs = {r["run_id"]: r for r in _pgd_runs(pgd_search)}
    points = [p for p in result.trajectory if not p.synthetic]
    assert len(points) == result.points_used == len(runs)
    assert {str(p.run_id) for p in points} == set(runs)
    for point in points:
        run = runs[str(point.run_id)]
        assert run["level"] == pytest.approx(point.level)
        # `scope` bị bỏ khỏi JSON khi bằng `full` (contract): đọc qua `RunView`.
        assert RunView.model_validate(run).scope == point.scope
        assert run["search_order"] == point.order
        assert run["status"] in ("completed", "skipped"), run
    assert {p.scope for p in points} == {EvalScope.SUBSET, EvalScope.FULL}
    assert [p.order for p in sorted(result.trajectory, key=lambda p: p.order)] == list(
        range(len(result.trajectory))
    )


def test_grid_runs_before_search(pgd_search: PgdSearch) -> None:
    names = [name for name, _ in pgd_search.recorder.applied]
    assert "fgsm" in names and "pgd_linf" in names
    last_grid = max(i for i, n in enumerate(names) if n == "fgsm")
    first_search = min(i for i, n in enumerate(names) if n == "pgd_linf")
    assert last_grid < first_search


def test_interim_result_updated_after_each_point(pgd_search: PgdSearch) -> None:
    rec = pgd_search.recorder
    interim = rec.interim("pgd_linf")
    final = rec.final("pgd_linf")
    assert len(final) == 1
    used = [r.points_used for r in interim]
    assert used == list(range(1, len(used) + 1))  # một bản tạm thời sau mỗi điểm
    assert len(used) == final[0].points_used - 1  # điểm cuối đi thẳng tới kết quả cuối
    # Đọc qua API trong lúc chạy cũng thấy bản tạm thời tăng dần.
    assert pgd_search.polled_points == sorted(pgd_search.polled_points)
    assert len(set(pgd_search.polled_points)) >= 2


def test_dynamic_runs_after_grid_and_never_early_stopped(pgd_search: PgdSearch) -> None:
    grid = [r for r in pgd_search.runs if r["attack_spec_id"] == FGSM_ID]
    search = _pgd_runs(pgd_search)
    assert grid and search
    top_grid = max(pgd_search.ordinals[r["run_id"]] for r in grid)
    assert all(pgd_search.ordinals[r["run_id"]] > top_grid for r in search)
    # PGD làm model sụp từ eps 2 nhưng attack tìm ngưỡng không bị dừng sớm.
    for run in search:
        reason = run.get("status_reason") or {}
        assert reason.get("code") != "early_stop", run


def test_ranking_excludes_search_attack(pgd_search: PgdSearch) -> None:
    assert any(RunView.model_validate(r).scope == EvalScope.FULL for r in _pgd_runs(pgd_search))
    ranked = [entry["attack_spec_id"] for entry in pgd_search.detail["attack_ranking"]]
    assert ranked == [FGSM_ID]


# ---------------------------------------------------------------- tình huống riêng (FGSM)


def test_full_slice_point_reuses_grid_run(api: Any) -> None:
    """Run quét lưới FGSM eps 4 đã có (cùng seed, cùng mã nguồn): điểm toàn slice eps 4 của lần
    tìm ngưỡng trúng cache; điểm tập con cùng level thì không (tập ảnh khác)."""
    target, client, grid_id = setup(api, [attack("fgsm", [4])])
    api.work(target, grid_id)
    (grid_run,) = runs_of(client, grid_id)
    assert grid_run["status"] == "completed"

    target, client, search_id = setup(api, [search_attack("fgsm", **FGSM_SEARCH)])
    api.work(target, search_id)
    result = result_of(detail_of(client, search_id), "fgsm")
    assert result.status in BROKE, result
    runs = {r["run_id"]: r for r in runs_of(client, search_id)}
    full4 = [p for p in result.trajectory if p.scope == EvalScope.FULL and p.level == 4]
    sub4 = [p for p in result.trajectory if p.scope == EvalScope.SUBSET and p.level == 4]
    assert full4 and sub4
    cached = runs[str(full4[0].run_id)]
    assert cached["status"] == "skipped"
    assert (cached["status_reason"] or {}).get("code") == "cached"
    assert cached["cached_from_run_id"] == grid_run["run_id"]
    assert runs[str(sub4[0].run_id)]["status"] == "completed"


def test_small_time_limit_stops_with_current_bracket(
    api: Any, recorder: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mỗi batch (một run) báo như 100 giây; giới hạn 300 giây: dừng sau vài điểm."""
    original = WorkerClient.progress

    def slow(self: WorkerClient, run_id: UUID, body: ProgressReport) -> Any:
        return original(self, run_id, body.model_copy(update={"processing_seconds_delta": 100.0}))

    monkeypatch.setattr(WorkerClient, "progress", slow)
    target, client, experiment_id = setup(
        api, [search_attack("fgsm", **FGSM_SEARCH)], limit={"kind": "time", "value": "300"}
    )
    api.work(target, experiment_id)
    detail = detail_of(client, experiment_id)
    result = result_of(detail, "fgsm")
    assert result.status == SearchStatus.STOPPED_LIMIT
    assert Decimal(str(detail["processing_seconds_used"])) >= Decimal(300)
    last = recorder.interim("fgsm")[-1]
    assert result.bracket == last.bracket
    assert result.points_used < result.max_points
    assert result.breaking_point is None


def test_worker_dies_during_bisect_then_resumes(
    api: Any, recorder: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Worker chết ngay sau khi gửi bản tạm thời ở giai đoạn chia đôi trên tập con, rồi lần nữa
    ngay sau điểm toàn slice đầu tiên; worker thứ ba chạy xong. Không điểm nào được
    đánh giá lại, KTC của điểm toàn slice chạy ở phiên trước vẫn có."""

    def crash(result: SearchResult) -> None:
        if result.status is not None:
            return
        # `stage` của bản tạm thời là giai đoạn của điểm kế tiếp.
        has_full = any(p.scope == EvalScope.FULL and not p.synthetic for p in result.trajectory)
        if (recorder.session == 1 and result.stage == SearchStage.BISECT_SUBSET) or (
            recorder.session == 2 and has_full
        ):
            raise Crash

    recorder.on_report = crash
    target, client, experiment_id = setup(api, [search_attack("fgsm", **FGSM_SEARCH)])
    for session in (1, 2):
        recorder.session = session
        with pytest.raises(Crash):
            api.work(target, experiment_id)
        api.clock.advance(61)  # lease hết hạn
    recorder.session = 3
    api.work(target, experiment_id)

    detail = detail_of(client, experiment_id)
    result = result_of(detail, "fgsm")
    assert result.status in BROKE, result
    orders = [(s, body.search_order) for s, body in recorder.created]
    assert sorted(o for _, o in orders) == sorted({o for _, o in orders})  # không tạo lại
    assert {s for s, _ in orders} == {1, 2, 3}
    levels = [(name, level) for name, level in recorder.applied if name == "fgsm"]
    assert len(levels) == result.points_used  # mỗi điểm đánh giá đúng một lần
    full_session2 = {
        body.search_order for s, body in recorder.created if s == 2 and body.scope == EvalScope.FULL
    }
    assert full_session2
    by_order = {p.order: p for p in result.trajectory}
    for order in full_session2:
        assert by_order[order].drop_ci is not None
    assert len(runs_of(client, experiment_id)) == result.points_used


def test_cancel_during_search(api: Any, recorder: Recorder) -> None:
    target, client, experiment_id = setup(api, [search_attack("fgsm", **FGSM_SEARCH)])

    def cancel(result: SearchResult) -> None:
        if result.status is None and result.stage == SearchStage.BISECT_SUBSET:
            ok(post(client, f"/experiments/{experiment_id}/cancel"))
            time.sleep(0.5)  # luồng heartbeat nhận chỉ thị cancel

    recorder.on_report = cancel
    api.work(target, experiment_id, heartbeat=0.1)
    detail = detail_of(client, experiment_id)
    assert detail["status"] == "cancelled"
    result = result_of(detail, "fgsm")
    assert result.status == SearchStatus.STOPPED_LIMIT
    cancelled_at = next(r for r in recorder.interim("fgsm") if r.stage == SearchStage.BISECT_SUBSET)
    assert result.bracket == cancelled_at.bracket


def test_unrecoverable_point_error_fails_search_only(api: Any, recorder: Recorder) -> None:
    """FGSM ném lỗi ở eps 4 (estimator giả): tìm ngưỡng FGSM `failed` kèm thông điệp; tìm ngưỡng
    `fog` trong cùng experiment vẫn có kết quả."""
    original = api.perturbation_factory or build_perturbation

    def broken(spec: Any, estimator: Any) -> Any:
        perturbation = original(spec, estimator)
        if spec.name != "fgsm":
            return perturbation
        apply = perturbation.apply

        def maybe_fail(images: Any, targets: Any, level: float, seed: int, mask: Any = None) -> Any:
            if float(level) == 4.0:
                raise RuntimeError("estimator giả: lỗi không phục hồi")
            return apply(images, targets, level, seed, mask)

        perturbation.apply = maybe_fail
        return perturbation

    api.perturbation_factory = broken
    attacks = [
        search_attack("fgsm", **FGSM_SEARCH),
        search_attack("fog", threshold=0.2, lo=1, hi=5, tol=4 / 256),
    ]
    target, client, experiment_id = setup(api, attacks)
    api.work(target, experiment_id)
    detail = detail_of(client, experiment_id)
    failed = result_of(detail, "fgsm")
    assert failed.status == SearchStatus.FAILED
    assert failed.message
    other = result_of(detail, "fog")
    assert other.status is not None and other.status != SearchStatus.FAILED, other
