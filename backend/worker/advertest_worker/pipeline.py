"""Chạy một run trong worker (requirements.md Phase 3, Luồng xử lý của worker bước 3; Phase R1,
`### Điều phối`).

Fingerprint → `start` (`skip_cached` thì bỏ qua) → dựng perturbation qua registry (patch qua
`patch_perturbation`) → executor (mới hoặc từ checkpoint) → từng batch: `process_batch`, upload
checkpoint, `progress`, làm theo `WorkerDirective` → hoàn tất qua `RunFinisher`. Lỗi đi qua
`WORKER_POLICY`; hết VRAM giữa chừng thì giảm batch size và chạy lại batch.

`JobRunner` giữ lease, heartbeat, thứ tự run và directive; `RunPipeline` giữ mọi phụ thuộc của
việc chạy run (model, registry, cache, client) và dùng chung cho calibration.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

import httpx
import torch

from advertest_contracts.enums import EvalScope, RunStatus
from advertest_contracts.models import (
    AttackSpec,
    BundleRun,
    CostProfile,
    Environment,
    FingerprintInputs,
    ProgressReport,
    RunStartRequest,
    WorkerJobBundle,
)
from advertest_contracts.perturbation import Perturbation
from advertest_worker.cache import JobCache
from advertest_worker.client import LeaseLost, WorkerClient
from advertest_worker.errors import WORKER_POLICY, StopExperiment
from advertest_worker.finish import RunFinisher
from advertest_worker.patch import patch_perturbation
from advertest_worker.search import PointOutcome
from advertest_worker.state import JobState
from attacks.builders import PerturbationRegistry
from ml_core.models.adapter import ModelAdapter
from ml_core.runner.candidates import StoreCandidates
from ml_core.runner.env import describe_device, environment
from ml_core.runner.errors import ErrorAction
from ml_core.runner.executor import RunContext, RunExecutor, build_context, load_clean_predictions
from ml_core.runner.fingerprint import fingerprint
from ml_core.runner.paths import checkpoint_key, run_id_prefix
from ml_core.runner.perturbations import ModelSource, PerturbationFactory, gradient_estimator
from ml_core.search.subset import eval_image_ids_sha256, select_subset
from ml_core.store import PresignedStore

logger = logging.getLogger(__name__)
DEFAULT_BATCH_SIZE = 8  # chỉ dùng khi không có cost profile (calibration thất bại)
BatchHook = Callable[[UUID, Sequence[str]], None]


class RunPipeline:
    """Phụ thuộc và các bước chạy một run của worker."""

    def __init__(
        self,
        client: WorkerClient,
        cache: JobCache,
        device: str,
        *,
        url_http: httpx.Client,
        clock: Callable[[], datetime],
        on_batch: BatchHook | None,
        registry: PerturbationRegistry,
        perturbation_factory: PerturbationFactory,
        models: ModelSource,
    ) -> None:
        self.client = client
        self.cache = cache
        self.device = device
        self.url_http = url_http
        self.clock = clock
        self.on_batch = on_batch
        self.registry = registry
        self.perturbation_factory = perturbation_factory
        self.models = models
        self.errors = WORKER_POLICY

    def adapter(self, bundle: WorkerJobBundle) -> ModelAdapter:
        """Adapter của model (cache theo khóa trong `ModelProvider`); model nạp lười."""
        return self.models.get(bundle.model_card, bundle.inference_params, self.device)

    def build_perturbation(self, spec: AttackSpec, bundle: WorkerJobBundle) -> Perturbation:
        return self.perturbation_factory(spec, gradient_estimator(self.adapter(bundle)))

    def environment(self, bundle: WorkerJobBundle) -> Environment:
        return environment(self.device).model_copy(
            update={"compute_target_id": bundle.config.compute_target_id}
        )

    def inputs(self, job: JobState, run: BundleRun, spec: AttackSpec) -> FingerprintInputs:
        assert job.fingerprints is not None
        image_ids = self.image_ids(job, run)
        return job.fingerprints.inputs(
            spec,
            run.level,
            run.seed,
            patch_key=run.patch_key,
            eval_image_ids_sha256=(None if image_ids is None else eval_image_ids_sha256(image_ids)),
        )

    @staticmethod
    def image_ids(job: JobState, run: BundleRun) -> list[str] | None:
        """Ảnh của run trên tập con (Phase 7); `None` với run toàn slice."""
        if run.scope != EvalScope.SUBSET:
            return None
        attack = next(
            a for a in job.bundle.config.attacks if a.attack_spec_id == run.attack_spec_id
        )
        if attack.search is None:
            raise ValueError(f"Run {run.run_id} trên tập con nhưng attack không tìm ngưỡng")
        return select_subset(job.bundle.slice.image_ids, attack.seed, attack.search.subset_size)

    def context(self, job: JobState) -> RunContext:
        if job.context is None:
            bundle = job.bundle
            batch = min((p.batch_size for p in job.profiles.values()), default=DEFAULT_BATCH_SIZE)
            clean = load_clean_predictions(
                self.cache.store,
                job.loader,
                bundle.inference_params,
                lambda: self.adapter(bundle),
                batch,
                lambda: describe_device(self.device),
            )
            job.context = build_context(
                job.loader, clean, bundle.inference_params, bundle.failure_cases_per_run
            )
        return job.context

    # ------------------------------------------------------------------ một run

    def run(self, job: JobState, run_id: UUID, spec: AttackSpec) -> None:
        self._run_one(job, run_id, spec, self.inputs(job, job.runs[run_id], spec))

    def _run_one(
        self, job: JobState, run_id: UUID, spec: AttackSpec, inputs: FingerprintInputs
    ) -> None:
        bundle, lease = job.bundle, job.lease
        run = job.runs[run_id]
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
            metrics = cached.metrics if cached else None
            job.ledger.record(run_id, RunStatus.SKIPPED, metrics)
            job.outcomes[run_id] = PointOutcome(RunStatus.SKIPPED, metrics)
            return

        store = PresignedStore(
            lambda key, method: self.client.artifact_url(run_id, lease.lease_id, key, method),
            self.url_http,
        )
        prefix = run_id_prefix(run_id)
        image_ids = self.image_ids(job, run)
        images_total = len(image_ids) if image_ids is not None else len(bundle.slice.image_ids)
        finish = RunFinisher(
            self.client,
            self.device,
            job,
            run,
            spec,
            fp,
            inputs,
            store,
            prefix,
            images_total=images_total,
        )

        executor: RunExecutor | None = None
        try:
            # Nạp model nằm trong `try` (tồn đọng R1 Group 5): lỗi của `ModelProvider.get` chỉ làm
            # run này `failed`, các run sau vẫn chạy.
            if spec.requires_gradients and not self.adapter(bundle).capabilities.gradients:
                finish.skipped(f"{spec.name} cần gradient nhưng model không hỗ trợ gradient")
                return
            if spec.requires_training:
                perturbation: Perturbation
                perturbation, finish.extra_seconds = patch_perturbation(
                    job,
                    run_id,
                    spec,
                    store,
                    cache=self.cache,
                    client=self.client,
                    clock=self.clock,
                    adapter=lambda: self.adapter(bundle),
                    registry=self.registry,
                )
            else:
                perturbation = self.build_perturbation(spec, bundle)
            builder = self.registry.builder_for(spec)
            candidates = StoreCandidates(
                store, prefix, builder.linf_eps(spec, run.level), builder.image_kind
            )
            # Checkpoint hỏng hoặc không tải được: run failed, run khác chạy tiếp.
            executor, batch_index = self._executor(
                job, run_id, fp, run.level, run.seed, perturbation, candidates, image_ids
            )
            self._run_batches(job, run_id, spec, store, prefix, finish, executor, batch_index)
        except Exception as exc:  # bảng `WORKER_POLICY`
            decision = self.errors.decide(exc)
            if decision.action is ErrorAction.PROPAGATE:
                raise
            finish.ended(decision, exc, executor)
            if decision.stops_experiment:
                raise StopExperiment from exc

    def _run_batches(
        self,
        job: JobState,
        run_id: UUID,
        spec: AttackSpec,
        store: PresignedStore,
        prefix: str,
        finish: RunFinisher,
        executor: RunExecutor,
        batch_index: int,
    ) -> None:
        lease, run = job.lease, job.runs[run_id]
        profile = job.profiles.get(spec.id)
        batch_size = profile.batch_size if profile else DEFAULT_BATCH_SIZE
        # Checkpoint mà API đang trỏ tới (từ bundle khi chạy tiếp); bị xóa khi có checkpoint mới.
        previous_key = run.checkpoint.key if run.checkpoint is not None else None
        while executor.remaining_ids():
            directive = job.box.current()
            if directive is not None and directive.action == "cancel":
                finish.cancelled(executor)
                raise StopExperiment
            if directive is not None and directive.action == "stop_limit":
                finish.stopped(executor)
                raise StopExperiment
            next_size = min(batch_size, len(executor.remaining_ids()))
            if (
                profile is not None
                and job.remaining_seconds is not None
                and profile.sec_per_image * next_size > job.remaining_seconds
            ):
                logger.info("Không đủ thời gian cho batch kế tiếp; dừng")
                finish.stopped(executor)
                raise StopExperiment
            batch = next(executor.batches(job.loader, batch_size))
            try:
                elapsed = executor.process_batch(batch)
            except Exception as exc:
                retry = self.errors.decide(exc).action is ErrorAction.RETRY_SMALLER
                if not retry or batch_size == 1:
                    raise
                batch_size = self._shrink_batch(job, spec, profile, batch_size)
                profile = job.profiles.get(spec.id)
                continue
            key = checkpoint_key(prefix, batch_index)
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
            job.apply(directive)
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
                raise StopExperiment
            if directive.action == "stop_limit" and executor.remaining_ids():
                finish.stopped(executor)
                raise StopExperiment
        finish.completed(executor)

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
        job: JobState,
        run_id: UUID,
        fp: str,
        level: float,
        seed: int,
        perturbation: Perturbation,
        candidates: StoreCandidates,
        image_ids: list[str] | None = None,
    ) -> tuple[RunExecutor, int]:
        run = job.runs[run_id]
        context = self.context(job)
        args: dict[str, Any] = {
            "fingerprint": fp,
            "level": level,
            "seed": seed,
            "perturbation": perturbation,
            "estimator": self.adapter(job.bundle),
            "context": context if image_ids is None else context.restricted(image_ids),
            "candidates": candidates,
        }
        if run.checkpoint is None:
            return RunExecutor(**args), 0
        data = self.url_http.get(run.checkpoint.url).raise_for_status().json()
        logger.info("Chạy tiếp từ checkpoint batch %d", run.checkpoint.batch_index)
        return RunExecutor.from_checkpoint(data, **args), run.checkpoint.batch_index + 1

    def _shrink_batch(
        self, job: JobState, spec: AttackSpec, profile: CostProfile | None, batch_size: int
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
