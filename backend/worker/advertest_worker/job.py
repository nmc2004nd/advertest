"""Chạy một experiment đã lease (requirements.md Phase 3, Luồng xử lý của worker; plan.md
task 24-28, 30).

1. Lấy bundle, tải tài nguyên còn thiếu vào cache.
2. Calibration cho attack chưa có cost profile.
3. Với từng run theo thứ tự: fingerprint → `start` → (`skip_cached` thì bỏ qua) → từng batch:
   `RunExecutor.process_batch`, upload checkpoint (ứng viên đã upload trong `process_batch`),
   `progress`, làm theo `WorkerDirective` → hoàn tất và `complete`.
4. Heartbeat chạy ở luồng riêng. Mất lease (`409`) thì dừng experiment, không gửi gì thêm.

Chạy tiếp sau gián đoạn: bundle có checkpoint mới nhất của run đang chạy dở; executor dựng lại
từ checkpoint và chỉ xử lý ảnh chưa xử lý.
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
import numpy as np
import torch

from advertest_contracts.enums import RunStatus, SkipReason, StopReason
from advertest_contracts.models import (
    AttackSpec,
    CostProfile,
    Environment,
    FailureCaseRecord,
    FingerprintInputs,
    Manifest,
    Progress,
    ProgressReport,
    RunCompletion,
    RunMetrics,
    RunResult,
    RunSkipRequest,
    RunStartRequest,
    StatusReason,
    WorkerDirective,
    WorkerJobBundle,
    WorkerLease,
)
from advertest_contracts.perturbation import Perturbation
from advertest_worker.cache import JobCache
from advertest_worker.calibrate import calibrate, calibration_patch, patch_training_cost
from advertest_worker.client import LeaseLost, WorkerClient
from advertest_worker.config import HEARTBEAT_INTERVAL_S
from advertest_worker.early_stop import RunLedger
from advertest_worker.patch import PatchInterrupted, PatchJob, obtain_patch
from attacks.art_adapter import IncompatibleAttack
from attacks.factory import build_perturbation
from attacks.patch.adapter import PatchPerturbation
from attacks.patch.geometry import patch_key
from ml_core.cli.evaluate import load_model_from_store
from ml_core.models.estimator import build_estimator
from ml_core.models.register import lib_versions
from ml_core.runner.cache_loader import ShaCacheLoader
from ml_core.runner.candidates import StoreCandidates
from ml_core.runner.env import describe_device, docker_image_digest, environment, git_state
from ml_core.runner.executor import (
    RunContext,
    RunExecutor,
    build_context,
    linf_eps,
    load_clean_predictions,
)
from ml_core.runner.fingerprint import build_fingerprint_inputs, fingerprint
from ml_core.runner.images import letterbox_mask, perturbation_kind
from ml_core.store import PresignedStore

logger = logging.getLogger(__name__)
DEFAULT_BATCH_SIZE = 8  # chỉ dùng khi không có cost profile (calibration thất bại)
ARTIFACTS_URI = "s3://artifacts/"
BatchHook = Callable[[UUID, Sequence[str]], None]


def utcnow() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------- heartbeat


@dataclass
class DirectiveBox:
    """Chỉ thị mới nhất từ API (heartbeat hoặc progress), dùng chung giữa hai luồng."""

    directive: WorkerDirective | None = None
    lease_lost: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)

    def update(self, directive: WorkerDirective) -> None:
        with self.lock:
            self.directive = directive

    def current(self) -> WorkerDirective | None:
        with self.lock:
            if self.lease_lost:
                raise LeaseLost(409, "conflict", "Lease đã mất (heartbeat)")
            return self.directive


class Heartbeat(threading.Thread):
    def __init__(
        self,
        client: WorkerClient,
        lease: WorkerLease,
        box: DirectiveBox,
        interval_s: float = HEARTBEAT_INTERVAL_S,
    ) -> None:
        super().__init__(daemon=True, name="heartbeat")
        self.client = client
        self.lease = lease
        self.box = box
        self.interval_s = interval_s
        self._stop_event = threading.Event()

    def run(self) -> None:
        while not self._stop_event.wait(self.interval_s):
            try:
                directive = self.client.heartbeat(self.lease.lease_id, self.lease.experiment_id)
            except LeaseLost:
                with self.box.lock:
                    self.box.lease_lost = True
                return
            except Exception:  # mạng chập chờn: client đã retry; lần sau thử tiếp
                logger.warning("Heartbeat thất bại", exc_info=True)
                continue
            self.box.update(directive)

    def stop(self) -> None:
        self._stop_event.set()
        if self.is_alive():
            self.join(timeout=self.interval_s + 5)


# ---------------------------------------------------------------- chạy job


class _StopExperiment(Exception):
    """Run kết thúc vì bị hủy hoặc chạm giới hạn: không chạy các run sau."""


@dataclass
class _Job:
    lease: WorkerLease
    bundle: WorkerJobBundle
    loader: ShaCacheLoader
    box: DirectiveBox
    environment: Environment
    profiles: dict[UUID, CostProfile]
    specs: dict[UUID, AttackSpec]
    remaining_seconds: float | None
    ledger: RunLedger
    context: RunContext | None = None


class JobRunner:
    def __init__(
        self,
        client: WorkerClient,
        cache: JobCache,
        device: str,
        *,
        url_http: httpx.Client | None = None,
        heartbeat_interval_s: float = HEARTBEAT_INTERVAL_S,
        clock: Callable[[], datetime] = utcnow,
        on_batch: BatchHook | None = None,
    ) -> None:
        self.client = client
        self.cache = cache
        self.device = device
        self.url_http = url_http or httpx.Client(timeout=120.0)
        self.heartbeat_interval_s = heartbeat_interval_s
        self.clock = clock
        self.on_batch = on_batch
        self._estimators: dict[str, Any] = {}

    # ------------------------------------------------------------------ chuẩn bị

    def _estimator(self, bundle: WorkerJobBundle) -> Any:
        sha = bundle.model_card.weights_sha256
        if sha not in self._estimators:
            model = load_model_from_store(self.cache.store, sha)
            self._estimators[sha] = build_estimator(model, bundle.inference_params, self.device)
        return self._estimators[sha]

    def _environment(self, bundle: WorkerJobBundle) -> Environment:
        return environment(self.device).model_copy(
            update={"compute_target_id": bundle.config.compute_target_id}
        )

    def calibrate_bundle(
        self, bundle: WorkerJobBundle, loader: ShaCacheLoader, *, force: bool = False
    ) -> dict[UUID, CostProfile]:
        """Cost profile cho mọi attack của bundle; đo (và gửi lên API) attack chưa có profile,
        hoặc mọi attack khi `force`. Attack không dùng được với model thì bỏ qua."""
        profiles = {p.attack_spec_id: p for p in bundle.cost_profiles}
        card = bundle.model_card
        for attack in bundle.config.attacks:
            spec = next(s for s in bundle.attack_specs if s.id == attack.attack_spec_id)
            if (spec.id in profiles and not force) or (
                spec.requires_gradients and not card.supports_gradients
            ):
                continue
            levels = [r.level for r in bundle.runs if r.attack_spec_id == spec.id]
            level = levels[0] if levels else spec.primary_param.min
            try:
                if spec.requires_training:
                    # Phase 6: đánh giá đo bằng patch ngẫu nhiên; chi phí train đo riêng bên dưới.
                    perturbation: Perturbation = calibration_patch(spec, loader)
                    level = spec.primary_param.max
                else:
                    perturbation = build_perturbation(spec, self._estimator(bundle))
            except Exception:
                logger.warning("Không dựng được %s để calibration", spec.name, exc_info=True)
                continue
            profile = calibrate(
                loader=loader,
                estimator=self._estimator(bundle),
                perturbation=perturbation,
                level=level,
                seed=attack.seed,
                device=self.device,
                compute_target_id=bundle.config.compute_target_id,
                model_version_id=card.id,
                attack_spec_id=spec.id,
                environment=self._environment(bundle),
                now=self.clock(),
            )
            if spec.requires_training:
                try:
                    seconds = patch_training_cost(spec, loader, self._estimator(bundle))
                except Exception:  # thiếu chi phí train chỉ làm ước lượng thiếu, không dừng job
                    logger.warning("Không đo được chi phí train %s", spec.name, exc_info=True)
                else:
                    profile = profile.model_copy(update={"sec_per_image_iteration": seconds})
            logger.info(
                "Calibration %s: batch %d, %.3f s/ảnh",
                spec.name,
                profile.batch_size,
                profile.sec_per_image,
            )
            self.client.cost_profile(profile)
            profiles[spec.id] = profile
        return profiles

    # ------------------------------------------------------------------ một experiment

    def run_lease(self, lease: WorkerLease) -> None:
        bundle = self.client.bundle(lease.experiment_id)
        loader = self.cache.prepare(bundle)
        box = DirectiveBox()
        heartbeat = Heartbeat(self.client, lease, box, self.heartbeat_interval_s)
        heartbeat.start()
        try:
            self._run_bundle(lease, bundle, loader, box)
        except LeaseLost:
            logger.warning("Mất lease của experiment %s; dừng", lease.experiment_id)
        finally:
            heartbeat.stop()

    def _run_bundle(
        self, lease: WorkerLease, bundle: WorkerJobBundle, loader: ShaCacheLoader, box: DirectiveBox
    ) -> None:
        limit = bundle.limit
        job = _Job(
            lease=lease,
            bundle=bundle,
            loader=loader,
            box=box,
            environment=self._environment(bundle),
            profiles=self.calibrate_bundle(bundle, loader),
            specs={s.id: s for s in bundle.attack_specs},
            remaining_seconds=(float(limit.value - limit.used) if limit.kind == "time" else None),
            ledger=RunLedger(bundle),
        )
        git = git_state()
        versions = lib_versions()
        digest = docker_image_digest()
        for run in bundle.runs:
            if run.status not in (RunStatus.QUEUED, RunStatus.RUNNING):
                continue
            directive = box.current()
            if directive is not None and directive.action != "continue":
                logger.info("Dừng experiment theo chỉ thị %s", directive.action)
                return
            spec = job.specs[run.attack_spec_id]
            if self._skip_early_stop(job, run.run_id, spec.name, run.level):
                continue
            inputs = build_fingerprint_inputs(
                spec=spec,
                level=run.level,
                seed=run.seed,
                params=bundle.inference_params,
                mapping=bundle.class_mapping,
                slice_spec=bundle.slice,
                weights_sha256=bundle.model_card.weights_sha256,
                git_commit=git.commit,
                git_dirty=git.dirty,
                lib_versions=versions,
                docker_image_digest=digest,
                patch_key=run.patch_key,
            )
            try:
                self._run_one(job, run.run_id, spec, inputs)
            except _StopExperiment:
                return

    def _skip_early_stop(self, job: _Job, run_id: UUID, name: str, level: float) -> bool:
        """Phase 6 (plan task 16): bỏ run `queued` khi level nhỏ hơn của cùng attack đã làm model
        sụp."""
        if job.ledger.status(run_id) != RunStatus.QUEUED:
            return False
        stop = job.ledger.decision(run_id)
        if stop is None:
            return False
        self.client.skip(
            run_id,
            RunSkipRequest(
                lease_id=job.lease.lease_id,
                code="early_stop",
                trigger_run_id=stop.trigger_run_id,
                message=f"Bỏ qua: model đã sụp ở level {stop.trigger_level:g}",
            ),
        )
        job.ledger.record(run_id, RunStatus.SKIPPED)
        logger.info("[%s %g] bỏ qua: dừng sớm (sụp ở %g)", name, level, stop.trigger_level)
        return True

    def _context(self, job: _Job) -> RunContext:
        if job.context is None:
            bundle = job.bundle
            batch = min((p.batch_size for p in job.profiles.values()), default=DEFAULT_BATCH_SIZE)
            clean = load_clean_predictions(
                self.cache.store,
                job.loader,
                bundle.inference_params,
                lambda: self._estimator(bundle),
                batch,
                lambda: describe_device(self.device),
            )
            job.context = build_context(
                job.loader, clean, bundle.inference_params, bundle.failure_cases_per_run
            )
        return job.context

    # ------------------------------------------------------------------ một run

    def _run_one(
        self, job: _Job, run_id: UUID, spec: AttackSpec, inputs: FingerprintInputs
    ) -> None:
        bundle, lease = job.bundle, job.lease
        run = next(r for r in bundle.runs if r.run_id == run_id)
        fp = fingerprint(inputs)
        response = self.client.start(
            run_id,
            RunStartRequest(
                lease_id=lease.lease_id,
                fingerprint=fp,
                fingerprint_inputs=inputs,
                environment=job.environment,
            ),
        )
        if response.action == "skip_cached":
            logger.info("[%s %g] bỏ qua: trùng fingerprint", spec.name, run.level)
            cached = response.cached_result
            job.ledger.record(run_id, RunStatus.SKIPPED, cached.metrics if cached else None)
            return

        store = PresignedStore(
            lambda key, method: self.client.artifact_url(run_id, lease.lease_id, key, method),
            self.url_http,
        )
        prefix = f"runs/{run_id}"
        finish = _Finisher(self, job, run_id, spec, run.level, fp, inputs, store, prefix)

        if spec.requires_gradients and not bundle.model_card.supports_gradients:
            finish.skipped(f"{spec.name} cần gradient nhưng model không hỗ trợ gradient")
            return
        try:
            if spec.requires_training:
                perturbation: Perturbation
                perturbation, finish.extra_seconds = self._patch_perturbation(
                    job, run_id, spec, store
                )
            else:
                perturbation = build_perturbation(spec, self._estimator(bundle))
        except IncompatibleAttack as exc:
            finish.skipped(str(exc))
            return
        except PatchInterrupted as exc:  # hủy hoặc chạm giới hạn giữa lúc train patch
            finish.extra_seconds = exc.seconds
            if exc.directive.action == "cancel":
                finish.cancelled(None)
            else:
                finish.stopped(None)
            raise _StopExperiment from exc
        except LeaseLost:
            raise
        except Exception as exc:  # lỗi khi dựng attack: run này failed, run khác chạy tiếp
            finish.failed(exc, None)
            return

        candidates = StoreCandidates(
            store, prefix, linf_eps(spec, perturbation, run.level), perturbation_kind(spec)
        )
        try:
            executor, batch_index = self._executor(
                job, run_id, fp, run.level, run.seed, perturbation, candidates
            )
        except LeaseLost:
            raise
        except Exception as exc:  # checkpoint hỏng hoặc không tải được: run failed, run khác chạy
            finish.failed(exc, None)
            return
        profile = job.profiles.get(spec.id)
        batch_size = profile.batch_size if profile else DEFAULT_BATCH_SIZE
        # Checkpoint mà API đang trỏ tới (từ bundle khi chạy tiếp); bị xóa khi có checkpoint mới.
        previous_key = run.checkpoint.key if run.checkpoint is not None else None
        try:
            while executor.remaining_ids():
                directive = job.box.current()
                if directive is not None and directive.action == "cancel":
                    finish.cancelled(executor)
                    raise _StopExperiment
                if directive is not None and directive.action == "stop_limit":
                    finish.stopped(executor)
                    raise _StopExperiment
                next_size = min(batch_size, len(executor.remaining_ids()))
                if (
                    profile is not None
                    and job.remaining_seconds is not None
                    and profile.sec_per_image * next_size > job.remaining_seconds
                ):
                    logger.info("Không đủ thời gian cho batch kế tiếp; dừng")
                    finish.stopped(executor)
                    raise _StopExperiment
                batch = next(executor.batches(job.loader, batch_size))
                try:
                    elapsed = executor.process_batch(batch)
                except torch.cuda.OutOfMemoryError:
                    if batch_size == 1:
                        raise
                    batch_size = self._shrink_batch(job, spec, profile, batch_size)
                    profile = job.profiles.get(spec.id)
                    continue
                key = f"{prefix}/checkpoints/{batch_index}.json"
                store.put(key, json.dumps(executor.to_checkpoint()).encode())
                directive = self.client.progress(
                    run_id,
                    ProgressReport(
                        lease_id=lease.lease_id,
                        images_done=executor.images_done,
                        batch_index=batch_index,
                        checkpoint_key=key,
                        processing_seconds_delta=elapsed,
                    ),
                )
                job.box.update(directive)
                job.remaining_seconds = directive.remaining_seconds
                self._drop_checkpoint(store, previous_key, key)
                previous_key = key
                batch_index += 1
                logger.info(
                    "[%s %g] %d/%d ảnh",
                    spec.name,
                    run.level,
                    executor.images_done,
                    executor.images_total,
                )
                if self.on_batch is not None:
                    self.on_batch(run_id, batch.image_ids)
                # Dừng ngay sau batch hiện tại (requirements.md, Luồng xử lý bước 5): hủy luôn
                # thắng; chạm giới hạn chỉ dừng khi còn ảnh chưa xử lý.
                if directive.action == "cancel":
                    finish.cancelled(executor)
                    raise _StopExperiment
                if directive.action == "stop_limit" and executor.remaining_ids():
                    finish.stopped(executor)
                    raise _StopExperiment
            finish.completed(executor)
        except (LeaseLost, _StopExperiment):
            raise
        except Exception as exc:  # một run lỗi không dừng các run khác
            finish.failed(exc, executor)

    def _patch_perturbation(
        self, job: _Job, run_id: UUID, spec: AttackSpec, store: PresignedStore
    ) -> tuple[PatchPerturbation, float]:
        """Phase 6 (plan task 17): lấy patch đã train (hoặc train trên slice huấn luyện, báo tiến
        độ `phase = training`), rồi dựng adapter dán patch. Trả kèm thời gian train để cộng vào
        `gpu_seconds` của run."""
        bundle = job.bundle
        run = next(r for r in bundle.runs if r.run_id == run_id)
        patch = next(p for p in bundle.patches if p.key == run.patch_key)
        training = next(s for s in bundle.training_slices if s.id == patch.training_slice_id)
        # Review Group 3 #2: không tin khóa và kích thước patch của bundle mà không đối chiếu.
        expected = patch_key(
            spec,
            weights_sha256=bundle.model_card.weights_sha256,
            training_slice_sha256=training.slice_sha256,
            area_ratio=run.level,
            seed=run.seed,
        )
        if patch.key != expected or patch.area_ratio != run.level:
            raise ValueError(
                f"Patch trong bundle ({patch.key}, area_ratio {patch.area_ratio}) không khớp run"
                f" (khóa tính lại {expected}, area_ratio {run.level})"
            )
        images = mask = None
        if patch.artifact is None:
            loader = self.cache.training_loader(bundle, training)
            loaded = [loader.load(image_id) for image_id in training.image_ids]
            images = np.stack([item[0] for item in loaded])
            mask = letterbox_mask([item[3] for item in loaded])

        def on_directive(directive: WorkerDirective) -> None:
            job.box.update(directive)
            job.remaining_seconds = directive.remaining_seconds

        obtained = obtain_patch(
            PatchJob(
                spec=spec,
                estimator=self._estimator(bundle),
                patch=patch,
                run_id=run_id,
                lease_id=job.lease.lease_id,
                seed=run.seed,
                weights_sha256=bundle.model_card.weights_sha256,
                training_slice_sha256=training.slice_sha256,
                store=store,
                client=self.client,
                clock=self.clock,
                on_directive=on_directive,
            ),
            images,
            mask,
        )
        return (
            PatchPerturbation(spec, obtained.patch, area_ratio=run.level),
            obtained.training_seconds,
        )

    @staticmethod
    def _drop_checkpoint(store: PresignedStore, previous: str | None, current: str) -> None:
        """Xóa checkpoint cũ sau khi API đã nhận checkpoint mới (`progress` thành công): API
        không còn trỏ tới nó. Checkpoint cuối cùng của run được giữ lại (xóa trước `complete`
        thì worker chết đúng lúc đó sẽ không chạy tiếp được). Lỗi khi xóa chỉ ghi cảnh báo, trừ
        mất lease."""
        if previous is None or previous == current:
            return
        try:
            store.delete(previous)
        except LeaseLost:
            raise  # mất lease: dừng experiment ngay, không xử lý thêm batch
        except Exception:
            logger.warning("Không xóa được checkpoint cũ %s", previous, exc_info=True)

    def _executor(
        self,
        job: _Job,
        run_id: UUID,
        fp: str,
        level: float,
        seed: int,
        perturbation: Perturbation,
        candidates: StoreCandidates,
    ) -> tuple[RunExecutor, int]:
        run = next(r for r in job.bundle.runs if r.run_id == run_id)
        args: dict[str, Any] = {
            "fingerprint": fp,
            "level": level,
            "seed": seed,
            "perturbation": perturbation,
            "estimator": self._estimator(job.bundle),
            "context": self._context(job),
            "candidates": candidates,
        }
        if run.checkpoint is None:
            return RunExecutor(**args), 0
        data = self.url_http.get(run.checkpoint.url).raise_for_status().json()
        logger.info("Chạy tiếp từ checkpoint batch %d", run.checkpoint.batch_index)
        return RunExecutor.from_checkpoint(data, **args), run.checkpoint.batch_index + 1

    def _shrink_batch(
        self, job: _Job, spec: AttackSpec, profile: CostProfile | None, batch_size: int
    ) -> int:
        """Hết VRAM giữa chừng: giảm batch size một bậc, gửi cost profile cập nhật."""
        smaller = max(1, batch_size // 2)
        logger.warning("Hết VRAM với batch %d; giảm còn %d", batch_size, smaller)
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        if profile is not None:
            updated = profile.model_copy(
                update={"batch_size": smaller, "measured_at": self.clock()}
            )
            self.client.cost_profile(updated)
            job.profiles[spec.id] = updated
        return smaller


# ---------------------------------------------------------------- hoàn tất run


class _Finisher:
    """Dựng `RunResult` + `RunCompletion` và gửi `complete` cho một run."""

    def __init__(
        self,
        runner: JobRunner,
        job: _Job,
        run_id: UUID,
        spec: AttackSpec,
        level: float,
        fp: str,
        inputs: FingerprintInputs,
        store: PresignedStore,
        prefix: str,
    ) -> None:
        self.runner = runner
        self.job = job
        self.run_id = run_id
        self.spec = spec
        self.level = level
        self.fp = fp
        self.inputs = inputs
        self.store = store
        self.prefix = prefix
        # Thời gian train patch của run (Phase 6): API ghi đè `gpu_seconds` của run bằng giá trị
        # gửi khi hoàn tất, nên phải cộng vào đây (review Group 3 #1).
        self.extra_seconds = 0.0

    def _manifest(self) -> str:
        manifest = Manifest(
            run_id=self.run_id,
            fingerprint=self.fp,
            fingerprint_inputs=self.inputs,
            environment=self.job.environment,
            created_at=self.runner.clock(),
        )
        key = f"{self.prefix}/manifest.json"
        self.store.put(key, (manifest.model_dump_json(indent=2) + "\n").encode())
        return ARTIFACTS_URI + key

    def _send(
        self,
        status: RunStatus,
        reason: StatusReason | None,
        executor: RunExecutor | None,
        metrics: RunMetrics | None = None,
        cases: list[FailureCaseRecord] | None = None,
    ) -> None:
        cases = cases or []
        images_total = len(self.job.bundle.slice.image_ids)
        result = RunResult(
            run_id=self.run_id,
            experiment_id=self.job.bundle.experiment_id,
            fingerprint=self.fp,
            attack_spec_id=self.spec.id,
            level=self.level,
            status=status,
            status_reason=reason,
            progress=Progress(
                images_done=executor.images_done if executor else 0, images_total=images_total
            ),
            metrics=metrics,
            gpu_seconds=(executor.processing_seconds if executor else 0.0) + self.extra_seconds,
            cost=None,
            failure_case_ids=[case.id for case in cases],
            manifest_uri=self._manifest(),
        )
        self.runner.client.complete(
            self.run_id,
            RunCompletion(lease_id=self.job.lease.lease_id, run_result=result, failure_cases=cases),
        )
        self.job.ledger.record(self.run_id, status, metrics)
        logger.info("[%s %g] %s", self.spec.name, self.level, status)

    def _discard_candidates(self, executor: RunExecutor | None) -> None:
        """Run không hoàn tất: ứng viên đã upload không phải kết quả, xóa đi."""
        if executor is None:
            return
        for image_id in executor.offered:
            try:
                executor.candidates.discard(image_id)
            except Exception:
                logger.warning("Không xóa được ứng viên %s", image_id, exc_info=True)

    def completed(self, executor: RunExecutor) -> None:
        finalized = executor.finalize(self.run_id)
        self._send(RunStatus.COMPLETED, None, executor, finalized.metrics, finalized.failure_cases)

    def stopped(self, executor: RunExecutor | None) -> None:
        reason = StatusReason(
            code=StopReason.TIME, message="Chạm giới hạn thời gian của experiment"
        )
        if executor is None or executor.images_done == 0:
            self._send(RunStatus.STOPPED_LIMIT, reason, executor)
            return
        finalized = executor.finalize(self.run_id, partial=True)
        self._send(
            RunStatus.STOPPED_LIMIT, reason, executor, finalized.metrics, finalized.failure_cases
        )

    def cancelled(self, executor: RunExecutor | None) -> None:
        self._discard_candidates(executor)
        self._send(
            RunStatus.CANCELLED,
            StatusReason(code="cancelled", message="Experiment bị hủy"),
            executor,
        )

    def skipped(self, message: str) -> None:
        self._send(
            RunStatus.SKIPPED, StatusReason(code=SkipReason.INCOMPATIBLE, message=message), None
        )

    def failed(self, exc: Exception, executor: RunExecutor | None) -> None:
        message = f"{type(exc).__name__}: {exc}"
        logger.error("[%s %g] failed: %s", self.spec.name, self.level, message, exc_info=exc)
        self._discard_candidates(executor)
        self._send(RunStatus.FAILED, StatusReason(code="error", message=message), executor)
