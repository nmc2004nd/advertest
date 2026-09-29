"""Vòng đời run do worker báo (requirements.md Phase 3: `start`, `progress`, `complete`,
`cost-profiles`; bảng Trạng thái).

Chỉ worker (qua API nội bộ) gọi các hàm này: người dùng không có đường nào ghi kết quả
(mission.md nguyên tắc 3). Mọi thay đổi trạng thái do API thực hiện.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from advertest_contracts.enums import ExperimentStatus, RunStatus, SkipReason, StopReason
from advertest_contracts.models import (
    ArtifactUrlRequest,
    ArtifactUrlResponse,
    CostProfile,
    FailureCaseRecord,
    Progress,
    ProgressReport,
    RunCompletion,
    RunMetrics,
    RunResult,
    RunStartRequest,
    RunStartResponse,
    StatusReason,
    WorkerDirective,
)
from backend.app import storage
from backend.app.db import models as m
from backend.app.presign import Presigner
from backend.app.services import leasing
from backend.app.services.clock import Clock, utcnow
from backend.app.services.errors import Conflict, Forbidden, Invalid, NotFound
from backend.app.services.experiments import TERMINAL_RUN, reason, runs_of
from ml_core.store import validate_key


class RunInvalidated(Conflict):
    """Run đã được chuyển sang `failed` trong transaction này; người gọi phải commit trước khi
    trả lỗi 409 (khác các `Conflict` khác, vốn không đổi dữ liệu)."""


ExistsFn = Callable[[str], bool]  # khóa trong bucket artifacts đã có chưa
ARTIFACTS_URI = f"s3://{storage.BUCKET_ARTIFACTS}/"


def _run_for_worker(
    session: Session, target: m.ComputeTarget, run_id: UUID, lease_id: UUID
) -> tuple[m.Run, m.Experiment]:
    # Khóa experiment trước rồi mới khóa run, cùng thứ tự với `experiments.cancel` (tránh deadlock).
    found = session.get(m.Run, run_id)
    if found is None:
        raise NotFound(f"Không có run {run_id}")
    experiment = leasing.leased_experiment(session, target, found.experiment_id, lease_id)
    run = session.get(m.Run, run_id, with_for_update=True, populate_existing=True)
    if run is None:
        raise NotFound(f"Không có run {run_id}")
    return run, experiment


def failure_case_ids(session: Session, run_id: UUID) -> list[UUID]:
    return list(
        session.scalars(
            select(m.FailureCase.id)
            .where(m.FailureCase.run_id == run_id)
            .order_by(m.FailureCase.rank)
        )
    )


def result_of(session: Session, run: m.Run) -> RunResult:
    """`RunResult` của một run đã có fingerprint (đọc từ DB)."""
    if run.fingerprint is None:
        raise Conflict(f"Run {run.id} chưa có fingerprint")
    source = run.cached_from_run_id or run.id
    return RunResult(
        run_id=run.id,
        experiment_id=run.experiment_id,
        fingerprint=run.fingerprint,
        attack_spec_id=run.attack_spec_id,
        level=run.level,
        status=run.status,
        status_reason=(
            StatusReason.model_validate(run.status_reason) if run.status_reason else None
        ),
        progress=Progress(images_done=run.images_done, images_total=run.images_total),
        metrics=RunMetrics.model_validate(run.metrics) if run.metrics else None,
        gpu_seconds=run.gpu_seconds,
        cost=None,
        failure_case_ids=failure_case_ids(session, source),
        manifest_uri=run.manifest_uri,
        cached_from_run_id=run.cached_from_run_id,
    )


# ---------------------------------------------------------------- start


def start(
    session: Session,
    target: m.ComputeTarget,
    run_id: UUID,
    request: RunStartRequest,
    clock: Clock = utcnow,
) -> RunStartResponse:
    """Có run `completed` cùng fingerprint ở bất kỳ experiment nào → run này `skipped` (`cached`),
    metric chép từ run gốc. Ngược lại run `running`. Gọi lại khi chạy tiếp sau gián đoạn: run đang
    `running` với cùng fingerprint được chạy tiếp."""
    run, experiment = _run_for_worker(session, target, run_id, request.lease_id)
    if experiment.status != ExperimentStatus.RUNNING:
        raise Conflict(f"Experiment đang ở trạng thái {experiment.status}")
    leasing.extend(experiment, target, clock)
    if run.status == RunStatus.RUNNING:
        if run.fingerprint != request.fingerprint:
            # Chạy tiếp với môi trường khác (code, thư viện, image đổi): checkpoint không dùng
            # được cho fingerprint mới. Run này failed (không kẹt ở running), run khác chạy tiếp.
            run.status = RunStatus.FAILED
            run.status_reason = reason(
                "error", "Môi trường worker đổi giữa chừng; gửi lại experiment để chạy lại"
            )
            run.finished_at = clock()
            session.flush()
            _after_run(session, experiment, run, clock)
            raise RunInvalidated(
                "Run đang chạy với fingerprint khác (môi trường worker đã đổi); run đã chuyển"
                " sang failed"
            )
        session.flush()
        return RunStartResponse(action="run")
    if run.status != RunStatus.QUEUED:
        raise Conflict(f"Run đã ở trạng thái {run.status}")

    now = clock()
    origin = session.scalar(
        select(m.Run)
        .where(
            m.Run.fingerprint == request.fingerprint,
            m.Run.status == RunStatus.COMPLETED,
            m.Run.id != run.id,
        )
        .order_by(m.Run.finished_at, m.Run.id)
        .limit(1)
    )
    run.fingerprint = request.fingerprint
    run.started_at = now
    if origin is None:
        run.status = RunStatus.RUNNING
        session.flush()
        return RunStartResponse(action="run")

    run.status = RunStatus.SKIPPED
    run.status_reason = reason(
        SkipReason.CACHED, f"Fingerprint trùng run {origin.id} đã hoàn thành"
    )
    run.cached_from_run_id = origin.id
    run.metrics = origin.metrics
    run.images_done = origin.images_done
    run.manifest_uri = origin.manifest_uri
    run.finished_at = now
    session.flush()
    _after_run(session, experiment, run, clock)
    return RunStartResponse(
        action="skip_cached", cached_from_run_id=origin.id, cached_result=result_of(session, origin)
    )


# ---------------------------------------------------------------- progress


def progress(
    session: Session,
    target: m.ComputeTarget,
    run_id: UUID,
    report: ProgressReport,
    clock: Clock = utcnow,
) -> WorkerDirective:
    """Tiến độ sau một batch: cộng dồn thời gian xử lý vào run và experiment, lưu checkpoint."""
    run, experiment = _run_for_worker(session, target, run_id, report.lease_id)
    if run.status != RunStatus.RUNNING:
        raise Conflict(f"Run đang ở trạng thái {run.status}, không nhận tiến độ")
    if not report.images_done >= run.images_done or report.images_done > run.images_total:
        raise Invalid(
            f"images_done = {report.images_done} không hợp lệ (đã có {run.images_done},"
            f" tổng {run.images_total})"
        )
    if not report.checkpoint_key.startswith(storage.run_prefix(run.id)):
        raise Invalid("checkpoint_key phải nằm trong runs/<run_id>/")
    run.images_done = report.images_done
    run.checkpoint_key = report.checkpoint_key
    run.checkpoint_batch_index = report.batch_index
    run.gpu_seconds += report.processing_seconds_delta
    experiment.processing_seconds_used += Decimal(str(report.processing_seconds_delta))
    leasing.extend(experiment, target, clock)
    session.flush()
    return leasing.directive(experiment)


# ---------------------------------------------------------------- complete


def _artifact_key(uri: str, run_id: UUID) -> str:
    key = uri.removeprefix(ARTIFACTS_URI)
    try:
        validate_key(key)
    except ValueError:
        raise Invalid(f"Khóa artifact không hợp lệ: {uri}") from None
    if not key.startswith(storage.run_prefix(run_id)):
        raise Invalid(f"Artifact {uri} phải nằm trong runs/{run_id}/")
    return key


def _check_case(case: FailureCaseRecord, run_id: UUID, exists: ExistsFn) -> None:
    artifacts = case.artifacts
    if artifacts.clean_thumb is None or artifacts.adversarial_thumb is None:
        raise Invalid(f"Failure case {case.id} thiếu thumbnail")
    for key in (
        artifacts.clean_png,
        artifacts.adversarial_png,
        artifacts.perturbation_png,
        artifacts.clean_thumb,
        artifacts.adversarial_thumb,
    ):
        if not exists(_artifact_key(key, run_id)):
            raise Invalid(f"Artifact {key} chưa có trong MinIO")


def complete(
    session: Session,
    target: m.ComputeTarget,
    run_id: UUID,
    completion: RunCompletion,
    exists: ExistsFn,
    clock: Clock = utcnow,
) -> None:
    """Kết quả cuối của run đang `running`: kiểm tra theo trạng thái của run và artifact trong
    MinIO, ghi run và failure case, cập nhật trạng thái experiment."""
    run, experiment = _run_for_worker(session, target, run_id, completion.lease_id)
    if run.status != RunStatus.RUNNING:
        raise Conflict(f"Run đang ở trạng thái {run.status}, không nhận kết quả")
    result = completion.run_result
    mismatch = [
        name
        for name, ok in (
            ("run_id", result.run_id == run.id),
            ("experiment_id", result.experiment_id == experiment.id),
            ("fingerprint", result.fingerprint == run.fingerprint),
            ("attack_spec_id", result.attack_spec_id == run.attack_spec_id),
            ("level", result.level == run.level),
            ("images_total", result.progress.images_total == run.images_total),
        )
        if not ok
    ]
    if mismatch:
        raise Invalid(f"RunResult không khớp run: {', '.join(mismatch)}")
    if result.status in (RunStatus.QUEUED, RunStatus.RUNNING):
        raise Invalid(f"status = {result.status} không phải kết quả cuối")
    if result.status == RunStatus.COMPLETED and result.progress.images_done != run.images_total:
        raise Invalid("Run completed phải xử lý đủ ảnh của slice")
    if result.status == RunStatus.CANCELLED and experiment.status != ExperimentStatus.CANCELLED:
        raise Invalid("Run chỉ cancelled khi experiment bị hủy")
    if result.cost is not None:
        raise Invalid("Máy local không có chi phí (cost phải null)")
    if result.manifest_uri is not None and not exists(_artifact_key(result.manifest_uri, run.id)):
        raise Invalid(f"Manifest {result.manifest_uri} chưa có trong MinIO")
    for case in completion.failure_cases:
        _check_case(case, run.id, exists)

    run.status = result.status
    run.status_reason = (
        result.status_reason.model_dump(mode="json") if result.status_reason else None
    )
    run.images_done = result.progress.images_done
    run.metrics = result.metrics.model_dump(mode="json") if result.metrics else None
    run.gpu_seconds = result.gpu_seconds
    run.manifest_uri = result.manifest_uri
    run.finished_at = clock()
    for rank, case in enumerate(completion.failure_cases):
        session.add(
            m.FailureCase(
                id=case.id,
                run_id=run.id,
                image_id=case.image_id,
                severity_score=case.severity_score,
                fingerprint=case.fingerprint,
                rank=rank,
                lost_objects=case.lost_objects,
                new_false_positives=case.new_false_positives,
                detections=case.detections.model_dump(mode="json"),
                artifacts=case.artifacts.model_dump(mode="json"),
            )
        )
    leasing.extend(experiment, target, clock)
    session.flush()
    _after_run(session, experiment, run, clock)


def _after_run(session: Session, experiment: m.Experiment, run: m.Run, clock: Clock) -> None:
    """Sau khi một run kết thúc: chạm giới hạn thì các run chưa chạy `stopped_limit`
    (`images_done = 0`); mọi run kết thúc thì experiment `completed` (trừ khi đã bị hủy)."""
    now = clock()
    remaining = leasing.remaining_seconds(experiment)
    limit_hit = run.status == RunStatus.STOPPED_LIMIT or (remaining is not None and remaining <= 0)
    runs = runs_of(session, experiment.id)
    for other in runs:
        if other.status != RunStatus.QUEUED:
            continue
        if experiment.status == ExperimentStatus.CANCELLED:
            other.status = RunStatus.CANCELLED
            other.status_reason = reason("cancelled", "Experiment bị hủy")
            other.finished_at = now
        elif limit_hit:
            other.status = RunStatus.STOPPED_LIMIT
            other.status_reason = reason(
                StopReason.TIME, "Chạm giới hạn thời gian trước khi run bắt đầu"
            )
            other.images_done = 0
            other.finished_at = now
    if all(r.status in TERMINAL_RUN for r in runs):
        if experiment.status == ExperimentStatus.RUNNING:
            experiment.status = ExperimentStatus.COMPLETED
        experiment.lease_id = None
        experiment.lease_expires_at = None
    session.flush()


# ---------------------------------------------------------------- artifact URL


def artifact_url(
    session: Session,
    target: m.ComputeTarget,
    run_id: UUID,
    request: ArtifactUrlRequest,
    presigner: Presigner,
    clock: Clock = utcnow,
) -> ArtifactUrlResponse:
    """Presigned URL cho một khóa nằm trong `runs/<run_id>/` của run đang `running` (worker giữ
    đúng lease). Run đã kết thúc không xin được URL nữa: artifact của nó là bất biến."""
    run, _ = _run_for_worker(session, target, run_id, request.lease_id)
    if run.status != RunStatus.RUNNING:
        raise Conflict(f"Run đang ở trạng thái {run.status}, không cấp URL")
    if not request.key.startswith(storage.run_prefix(run.id)):
        raise Forbidden(f"Chỉ cấp URL trong runs/{run.id}/")
    signed = presigner.url(storage.BUCKET_ARTIFACTS, request.key, request.method, clock())
    return ArtifactUrlResponse(
        key=request.key, method=request.method, url=signed.url, expires_at=signed.expires_at
    )


# ---------------------------------------------------------------- cost profile


def record_cost_profile(
    session: Session, target: m.ComputeTarget, profile: CostProfile
) -> m.CostProfile:
    """Thêm cost profile của target (giữ lịch sử; profile mới nhất theo `measured_at` thắng)."""
    if profile.compute_target_id != target.id:
        raise Forbidden("Cost profile của compute target khác")
    if session.get(m.ModelVersion, profile.model_version_id) is None:
        raise NotFound(f"Không có model version {profile.model_version_id}")
    if session.get(m.AttackSpecRow, profile.attack_spec_id) is None:
        raise NotFound(f"Không có attack spec {profile.attack_spec_id}")
    row = m.CostProfile(
        compute_target_id=target.id,
        model_version_id=profile.model_version_id,
        attack_spec_id=profile.attack_spec_id,
        sec_per_image=profile.sec_per_image,
        peak_vram_mb=profile.peak_vram_mb,
        batch_size=profile.batch_size,
        measured_at=profile.measured_at,
        environment=profile.environment.model_dump(mode="json"),
    )
    session.add(row)
    session.flush()
    return row
