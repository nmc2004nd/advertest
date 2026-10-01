"""Tự tìm ngưỡng phía API (requirements.md Phase 7, mục API và Worker; plan task 21, 22, 23).

- `create_run`: run `queued` cho điểm tìm kiếm kế tiếp. Mọi vi phạm trả `Invalid` (422), không
  `Conflict` (409): worker coi 409 là mất lease.
- `submit_result`: `SearchResult` tạm thời hoặc cuối của worker; đối chiếu với run và cấu hình
  (chỉ worker ghi kết quả, kết quả phải khớp run đã chạy: mission.md nguyên tắc 3). Mỗi
  (experiment, attack) một dòng; bản cuối không bị thay.
- Experiment chỉ `completed` khi mọi run kết thúc **và** mọi attack tìm ngưỡng có kết quả cuối.
  Hủy hoặc hết thời gian mà kết quả còn tạm thời: API chốt thành `stopped_limit` với khoảng và quỹ
  đạo hiện có (quyết định Group 4; như API chốt trạng thái run ở `finish_cancelled`).
"""

from __future__ import annotations

import math
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from advertest_contracts.enums import (
    EvalScope,
    ExperimentStatus,
    RunStatus,
    SearchStage,
    SearchStatus,
)
from advertest_contracts.models import (
    AttackConfig,
    AttackSpec,
    BundleRun,
    ExperimentConfig,
    RunMetrics,
    SearchResult,
    SearchResultReport,
    SearchRunCreate,
)
from backend.app.db import models as m
from backend.app.services import leasing, notifications
from backend.app.services.clock import Clock, utcnow
from backend.app.services.errors import Conflict, Invalid, NotFound
from backend.app.services.experiment_config import spec_of
from backend.app.services.experiments import TERMINAL_RUN, runs_of
from ml_core.metrics.threshold import threshold_quantity
from ml_core.search.bounds import search_bounds, search_grid, uses_subset

DROP_TOLERANCE = 1e-9  # sai số khi so đại lượng worker gửi với đại lượng tính lại từ metric


class SearchStopped(Conflict):
    """Hết thời gian của experiment: API đã chốt kết quả và experiment trong transaction này;
    người gọi commit trước khi trả 409 (worker dừng experiment)."""


# ---------------------------------------------------------------- tra cứu


def _search_attack(experiment: m.Experiment, attack_spec_id: UUID) -> AttackConfig:
    config = ExperimentConfig.model_validate(experiment.config)
    attack = next((a for a in config.attacks if a.attack_spec_id == attack_spec_id), None)
    if attack is None:
        raise Invalid(f"Attack {attack_spec_id} không thuộc experiment")
    if attack.search is None:
        raise Invalid(f"Attack {attack_spec_id} không ở chế độ tự tìm ngưỡng")
    return attack


def _spec(session: Session, attack_spec_id: UUID) -> AttackSpec:
    row = session.get(m.AttackSpecRow, attack_spec_id)
    if row is None:
        raise NotFound(f"Không có attack spec {attack_spec_id}")
    return spec_of(row)


def _images(session: Session, experiment: m.Experiment) -> int:
    slice_row = session.get(m.Slice, experiment.slice_id)
    if slice_row is None:
        raise NotFound("Slice của experiment không còn")
    return len(slice_row.image_ids)


def results(session: Session, experiment_id: UUID) -> list[SearchResult]:
    """`SearchResult` mới nhất của từng attack tìm ngưỡng đã có điểm, theo thứ tự trong config."""
    experiment = session.get(m.Experiment, experiment_id)
    if experiment is None:
        return []
    rows = {
        row.attack_spec_id: row
        for row in session.scalars(
            select(m.SearchResultRow).where(m.SearchResultRow.experiment_id == experiment_id)
        )
    }
    order = [a.attack_spec_id for a in ExperimentConfig.model_validate(experiment.config).attacks]
    return [SearchResult.model_validate(rows[i].result) for i in order if i in rows]


def _search_ids(experiment: m.Experiment) -> list[UUID]:
    config = ExperimentConfig.model_validate(experiment.config)
    return [a.attack_spec_id for a in config.attacks if a.search is not None]


def pending(session: Session, experiment: m.Experiment) -> bool:
    """Còn attack tìm ngưỡng chưa có kết quả cuối."""
    final = {r.attack_spec_id for r in results(session, experiment.id) if r.status is not None}
    return any(i not in final for i in _search_ids(experiment))


def finalize_unfinished(session: Session, experiment: m.Experiment, clock: Clock = utcnow) -> None:
    """Kết quả tạm thời → `stopped_limit` (hủy hoặc hết thời gian khi worker không còn chốt)."""
    for row in session.scalars(
        select(m.SearchResultRow)
        .where(m.SearchResultRow.experiment_id == experiment.id)
        .with_for_update()
    ):
        result = SearchResult.model_validate(row.result)
        if result.status is not None:
            continue
        row.result = result.model_copy(
            update={"stage": SearchStage.DONE, "status": SearchStatus.STOPPED_LIMIT}
        ).model_dump(mode="json")
        row.updated_at = clock()
    session.flush()


def maybe_finish(session: Session, experiment: m.Experiment, clock: Clock = utcnow) -> None:
    """Experiment `running` → `completed` khi mọi run kết thúc và mọi tìm ngưỡng có kết quả cuối;
    bỏ lease. Gọi sau khi một run kết thúc hoặc một kết quả cuối được ghi."""
    runs = runs_of(session, experiment.id)
    if not all(r.status in TERMINAL_RUN for r in runs):
        return
    remaining = leasing.remaining_seconds(experiment)
    out_of_time = remaining is not None and remaining <= 0
    if experiment.status == ExperimentStatus.CANCELLED or out_of_time:
        finalize_unfinished(session, experiment, clock)
    elif pending(session, experiment):
        return  # worker còn tìm ngưỡng: giữ lease
    if experiment.status == ExperimentStatus.RUNNING:
        experiment.status = ExperimentStatus.COMPLETED
        experiment.finished_at = clock()
        notifications.enqueue_experiment_finished(session, experiment)
    experiment.lease_id = None
    experiment.lease_expires_at = None
    session.flush()


# ---------------------------------------------------------------- tạo run động (task 21)


def bundle_run(run: m.Run) -> BundleRun:
    return BundleRun(
        run_id=run.id,
        attack_spec_id=run.attack_spec_id,
        level=run.level,
        seed=run.seed,
        status=run.status,
        images_done=run.images_done,
        images_total=run.images_total,
        checkpoint=None,
        metrics=RunMetrics.model_validate(run.metrics) if run.metrics else None,
        scope=EvalScope(run.scope),
        search_order=run.search_order,
    )


def create_run(
    session: Session,
    target: m.ComputeTarget,
    experiment_id: UUID,
    body: SearchRunCreate,
    clock: Clock = utcnow,
) -> BundleRun:
    experiment = leasing.leased_experiment(session, target, experiment_id, body.lease_id)
    if experiment.status != ExperimentStatus.RUNNING:
        raise Conflict(f"Experiment đang ở trạng thái {experiment.status}")
    remaining = leasing.remaining_seconds(experiment)
    if remaining is not None and remaining <= 0:
        finalize_unfinished(session, experiment, clock)
        maybe_finish(session, experiment, clock)
        raise SearchStopped("Hết thời gian của experiment: không tạo thêm điểm tìm ngưỡng")
    attack = _search_attack(experiment, body.attack_spec_id)
    search = attack.search
    assert search is not None
    spec = _spec(session, body.attack_spec_id)
    images = _images(session, experiment)
    grid = search_grid(search, spec.primary_param)
    if grid.values is not None:
        if body.level not in grid.values:
            raise Invalid(
                f"Level {body.level:g} không phải giá trị của spec trong"
                f" [{search.lo:g}, {search.hi:g}]"
            )
    elif not search.lo <= body.level <= search.hi:
        raise Invalid(f"Level {body.level:g} ngoài [{search.lo:g}, {search.hi:g}]")
    subset = uses_subset(search, images)
    if body.scope == EvalScope.SUBSET and not subset:
        raise Invalid("Slice không lớn hơn tập con: mọi điểm đánh giá trên toàn slice")
    existing = [
        r
        for r in runs_of(session, experiment.id)
        if r.attack_spec_id == spec.id and r.search_order is not None
    ]
    max_points = search_bounds(search, spec.primary_param, images).max_points
    if len(existing) >= max_points:
        raise Invalid(f"Đã có {len(existing)} điểm, tối đa {max_points} (max_points)")
    if any(r.search_order == body.search_order for r in existing):
        raise Invalid(f"Đã có run với search_order {body.search_order}")
    ordinal = session.scalar(
        select(func.max(m.Run.ordinal)).where(m.Run.experiment_id == experiment.id)
    )
    run = m.Run(
        experiment_id=experiment.id,
        attack_spec_id=spec.id,
        level=float(body.level),
        params={spec.primary_param.name: float(body.level)},
        seed=attack.seed,
        images_total=search.subset_size if body.scope == EvalScope.SUBSET else images,
        status=RunStatus.QUEUED,
        ordinal=(ordinal if ordinal is not None else -1) + 1,
        scope=body.scope.value,
        search_order=body.search_order,
    )
    session.add(run)
    leasing.extend(experiment, target, clock)
    session.flush()
    return bundle_run(run)


# ---------------------------------------------------------------- SearchResult (task 22)


def _check_point_drop(run: m.Run, drop: float | None, attack: AttackConfig) -> None:
    search = attack.search
    assert search is not None
    metrics = RunMetrics.model_validate(run.metrics) if run.metrics else None
    usable = run.status in (RunStatus.COMPLETED, RunStatus.SKIPPED) and metrics is not None
    expected = (
        threshold_quantity(metrics, search.threshold_kind, search.class_filter)
        if usable and metrics is not None
        else None
    )
    if expected is None:
        if drop is not None:
            raise Invalid(f"Điểm của run {run.id} không có metric dùng được nhưng có drop")
        return
    if drop is None or not math.isclose(drop, expected, rel_tol=0, abs_tol=DROP_TOLERANCE):
        raise Invalid(f"drop của run {run.id} không khớp metric của run ({expected})")


def submit_result(
    session: Session,
    target: m.ComputeTarget,
    experiment_id: UUID,
    report: SearchResultReport,
    clock: Clock = utcnow,
) -> None:
    experiment = leasing.leased_experiment(session, target, experiment_id, report.lease_id)
    if experiment.status not in (ExperimentStatus.RUNNING, ExperimentStatus.CANCELLED):
        raise Conflict(f"Experiment đang ở trạng thái {experiment.status}")
    result = report.result
    if result.experiment_id != experiment.id:
        raise Invalid("SearchResult thuộc experiment khác")
    attack = _search_attack(experiment, result.attack_spec_id)
    search = attack.search
    assert search is not None
    if experiment.status == ExperimentStatus.CANCELLED and result.status not in (
        None,
        SearchStatus.STOPPED_LIMIT,
    ):
        raise Invalid("Experiment đã hủy: chỉ nhận kết quả stopped_limit")
    mismatch = [
        name
        for name, ok in (
            ("threshold_kind", result.threshold_kind == search.threshold_kind),
            ("threshold", result.threshold == search.threshold),
            ("class_filter", result.class_filter == search.class_filter),
        )
        if not ok
    ]
    if mismatch:
        raise Invalid(f"SearchResult không khớp cấu hình: {', '.join(mismatch)}")
    spec = _spec(session, result.attack_spec_id)
    max_points = search_bounds(search, spec.primary_param, _images(session, experiment)).max_points
    if result.max_points != max_points:
        raise Invalid(f"max_points phải là {max_points}")
    runs = {
        r.id: r
        for r in runs_of(session, experiment.id)
        if r.attack_spec_id == spec.id and r.search_order is not None
    }
    for point in result.trajectory:
        if point.run_id is None:
            continue
        run = runs.get(point.run_id)
        if run is None:
            raise Invalid(f"Run {point.run_id} không phải điểm tìm ngưỡng của attack này")
        if (run.search_order, run.level, run.scope) != (point.order, point.level, point.scope):
            raise Invalid(f"Điểm {point.order} không khớp run {run.id} (order, level, scope)")
        if run.status not in TERMINAL_RUN:
            raise Invalid(f"Run {run.id} chưa kết thúc")
        _check_point_drop(run, point.drop, attack)

    row = session.scalar(
        select(m.SearchResultRow)
        .where(
            m.SearchResultRow.experiment_id == experiment.id,
            m.SearchResultRow.attack_spec_id == spec.id,
        )
        .with_for_update()
    )
    if row is not None and SearchResult.model_validate(row.result).status is not None:
        raise Invalid("Kết quả cuối đã có, không thay được")
    payload = result.model_dump(mode="json")
    if row is None:
        # Experiment đang bị khóa (`leased_experiment`): không có ghi đồng thời cho cùng attack.
        session.add(
            m.SearchResultRow(
                experiment_id=experiment.id,
                attack_spec_id=spec.id,
                result=payload,
                updated_at=clock(),
            )
        )
    else:
        row.result = payload
        row.updated_at = clock()
    leasing.extend(experiment, target, clock)
    session.flush()
    if result.status is not None:
        maybe_finish(session, experiment, clock)
