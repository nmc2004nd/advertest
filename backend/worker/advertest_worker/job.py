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

Phase 7: chạy mọi run quét lưới trước, rồi lần lượt từng attack tìm ngưỡng (`SearchDriver`); run
của tìm ngưỡng được tạo động qua API, đánh giá trên tập con hoặc toàn slice theo `scope`. Mọi run
có metric ghi prediction theo ảnh (`runs/<run_id>/predictions.json`, dùng cho bootstrap).
"""

from __future__ import annotations

import json
import logging
import re
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
import numpy as np
import torch

from advertest_contracts.enums import EvalScope, RunMode, RunStatus, SkipReason, StopReason
from advertest_contracts.models import (
    AttackConfig,
    AttackSpec,
    BundleRun,
    CostProfile,
    Environment,
    FailureCaseRecord,
    FingerprintInputs,
    LibVersions,
    Manifest,
    Progress,
    ProgressReport,
    RunCompletion,
    RunMetrics,
    RunResult,
    RunSkipRequest,
    RunStartRequest,
    SearchResult,
    SearchResultReport,
    SearchRunCreate,
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
from advertest_worker.search import KnownRun, PointOutcome, SearchDriver
from attacks.art_adapter import IncompatibleAttack
from attacks.factory import build_perturbation
from attacks.patch.adapter import PatchPerturbation
from attacks.patch.geometry import patch_key
from ml_core.cli.evaluate import load_model_from_store
from ml_core.metrics.bootstrap import (
    dump_run_predictions,
    load_run_predictions,
    run_predictions_key,
)
from ml_core.metrics.filters import Prediction
from ml_core.models.estimator import build_estimator
from ml_core.models.register import lib_versions
from ml_core.runner.cache_loader import ShaCacheLoader
from ml_core.runner.candidates import StoreCandidates
from ml_core.runner.env import (
    GitState,
    describe_device,
    docker_image_digest,
    environment,
    git_state,
)
from ml_core.runner.executor import (
    RunContext,
    RunExecutor,
    build_context,
    linf_eps,
    load_clean_predictions,
)
from ml_core.runner.fingerprint import build_fingerprint_inputs, fingerprint
from ml_core.runner.images import letterbox_mask, perturbation_kind
from ml_core.search.subset import eval_image_ids_sha256, select_subset
from ml_core.store import KeyNotFoundError, PresignedStore

logger = logging.getLogger(__name__)
_PREDICTIONS_KEY = re.compile(r"runs/([0-9a-f-]{36})/predictions\.json")
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


@dataclass(frozen=True)
class _Provenance:
    """Nguồn gốc mã và môi trường cho fingerprint, đọc một lần mỗi experiment."""

    git: GitState
    versions: LibVersions
    digest: str


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
    # Phase 7: mọi run đã biết (bundle và run tạo động), kết quả của run trong phiên và prediction
    # theo ảnh của run đã hoàn tất trong phiên (bootstrap).
    runs: dict[UUID, BundleRun] = field(default_factory=dict)
    outcomes: dict[UUID, PointOutcome] = field(default_factory=dict)
    predictions: dict[UUID, dict[str, Prediction]] = field(default_factory=dict)
    provenance: _Provenance | None = None


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
            # Phase 7: attack tìm ngưỡng có thể chưa có run; đo ở `hi` (level 0 của PGD cho bước
            # nhảy 0).
            fallback = attack.search.hi if attack.search is not None else spec.primary_param.min
            level = levels[0] if levels else fallback
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
            runs={run.run_id: run for run in bundle.runs},
        )
        for run in bundle.runs:
            if run.search_order is not None:
                continue  # run tìm ngưỡng chạy trong vòng lặp tìm kiếm (Phase 7)
            if run.status not in (RunStatus.QUEUED, RunStatus.RUNNING):
                continue
            if self._directive_stops(job):
                return
            spec = job.specs[run.attack_spec_id]
            if self._skip_early_stop(job, run.run_id, spec.name, run.level):
                continue
            try:
                self._run_one(job, run.run_id, spec, self._inputs(job, run, spec))
            except _StopExperiment:
                return
        for attack in bundle.config.attacks:
            if attack.mode != RunMode.SEARCH:
                continue
            if self._directive_stops(job):
                return
            if self._search(job, attack):
                return

    @staticmethod
    def _directive_stops(job: _Job) -> bool:
        directive = job.box.current()
        if directive is not None and directive.action != "continue":
            logger.info("Dừng experiment theo chỉ thị %s", directive.action)
            return True
        return False

    def _inputs(self, job: _Job, run: BundleRun, spec: AttackSpec) -> FingerprintInputs:
        bundle = job.bundle
        if job.provenance is None:
            job.provenance = _Provenance(git_state(), lib_versions(), docker_image_digest())
        git, versions, digest = job.provenance.git, job.provenance.versions, job.provenance.digest
        image_ids = self._image_ids(job, run)
        return build_fingerprint_inputs(
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
            eval_image_ids_sha256=(None if image_ids is None else eval_image_ids_sha256(image_ids)),
        )

    @staticmethod
    def _image_ids(job: _Job, run: BundleRun) -> list[str] | None:
        """Ảnh của run trên tập con (Phase 7); `None` với run toàn slice."""
        if run.scope != EvalScope.SUBSET:
            return None
        attack = next(
            a for a in job.bundle.config.attacks if a.attack_spec_id == run.attack_spec_id
        )
        if attack.search is None:
            raise ValueError(f"Run {run.run_id} trên tập con nhưng attack không tìm ngưỡng")
        return select_subset(job.bundle.slice.image_ids, attack.seed, attack.search.subset_size)

    # ------------------------------------------------------------------ tìm ngưỡng (Phase 7)

    def _search(self, job: _Job, attack: AttackConfig) -> bool:
        """Một attack tìm ngưỡng; `True` nếu experiment phải dừng."""
        bundle = job.bundle
        spec = job.specs[attack.attack_spec_id]
        previous = next((r for r in bundle.search_results if r.attack_spec_id == spec.id), None)
        known = {
            run.search_order: KnownRun(run.run_id, run.level, run.scope, run.status, run.metrics)
            for run in bundle.runs
            if run.attack_spec_id == spec.id and run.search_order is not None
        }
        driver = SearchDriver(
            experiment_id=bundle.experiment_id,
            attack=attack,
            spec=spec,
            context=self._context(job),
            hooks=_JobSearchHooks(self, job, attack, spec),
            known_runs=known,
            previous=previous,
        )
        logger.info("[%s] tìm ngưỡng", spec.name)
        return driver.run()

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
        prefix = f"runs/{run_id}"
        image_ids = self._image_ids(job, run)
        images_total = len(image_ids) if image_ids is not None else len(bundle.slice.image_ids)
        finish = _Finisher(
            self, job, run, spec, fp, inputs, store, prefix, images_total=images_total
        )

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
                job, run_id, fp, run.level, run.seed, perturbation, candidates, image_ids
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
        run = job.runs[run_id]
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
        image_ids: list[str] | None = None,
    ) -> tuple[RunExecutor, int]:
        run = job.runs[run_id]
        context = self._context(job)
        args: dict[str, Any] = {
            "fingerprint": fp,
            "level": level,
            "seed": seed,
            "perturbation": perturbation,
            "estimator": self._estimator(job.bundle),
            "context": context if image_ids is None else context.restricted(image_ids),
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
        run: BundleRun,
        spec: AttackSpec,
        fp: str,
        inputs: FingerprintInputs,
        store: PresignedStore,
        prefix: str,
        *,
        images_total: int,
    ) -> None:
        self.runner = runner
        self.job = job
        self.run = run
        self.run_id = run.run_id
        self.spec = spec
        self.level = run.level
        self.images_total = images_total
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
        predictions_key: str | None = None,
    ) -> None:
        cases = cases or []
        result = RunResult(
            run_id=self.run_id,
            experiment_id=self.job.bundle.experiment_id,
            fingerprint=self.fp,
            attack_spec_id=self.spec.id,
            level=self.level,
            status=status,
            status_reason=reason,
            progress=Progress(
                images_done=executor.images_done if executor else 0,
                images_total=self.images_total,
            ),
            metrics=metrics,
            gpu_seconds=(executor.processing_seconds if executor else 0.0) + self.extra_seconds,
            cost=None,
            failure_case_ids=[case.id for case in cases],
            manifest_uri=self._manifest(),
            scope=self.run.scope,
            search_order=self.run.search_order,
            predictions_key=predictions_key,
        )
        self.runner.client.complete(
            self.run_id,
            RunCompletion(lease_id=self.job.lease.lease_id, run_result=result, failure_cases=cases),
        )
        self.job.ledger.record(self.run_id, status, metrics)
        message = reason.message if reason is not None else None
        self.job.outcomes[self.run_id] = PointOutcome(status, metrics, message)
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

    def _predictions(self, executor: RunExecutor) -> str:
        """Prediction theo ảnh của run (Phase 7, plan task 13a): upload để bootstrap dùng lại."""
        key = run_predictions_key(self.run_id)
        device = describe_device(self.runner.device)
        self.store.put(key, dump_run_predictions(self.run_id, executor.predictions, device))
        return key

    def completed(self, executor: RunExecutor) -> None:
        finalized = executor.finalize(self.run_id)
        key = self._predictions(executor)
        self._send(
            RunStatus.COMPLETED,
            None,
            executor,
            finalized.metrics,
            finalized.failure_cases,
            predictions_key=key,
        )
        self.job.predictions[self.run_id] = dict(executor.predictions)

    def stopped(self, executor: RunExecutor | None) -> None:
        reason = StatusReason(
            code=StopReason.TIME, message="Chạm giới hạn thời gian của experiment"
        )
        if executor is None or executor.images_done == 0:
            self._send(RunStatus.STOPPED_LIMIT, reason, executor)
            return
        finalized = executor.finalize(self.run_id, partial=True)
        self._send(
            RunStatus.STOPPED_LIMIT,
            reason,
            executor,
            finalized.metrics,
            finalized.failure_cases,
            predictions_key=self._predictions(executor),
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


# ---------------------------------------------------------------- hook của tìm ngưỡng (Phase 7)


class _JobSearchHooks:
    """`SearchHooks` của `SearchDriver` trên API và model thật."""

    def __init__(
        self, runner: JobRunner, job: _Job, attack: AttackConfig, spec: AttackSpec
    ) -> None:
        self.runner = runner
        self.job = job
        self.attack = attack
        self.spec = spec

    def should_stop(self) -> bool:
        directive = self.job.box.current()
        return directive is not None and directive.action != "continue"

    def create_run(self, attack_spec_id: UUID, level: float, scope: EvalScope, order: int) -> UUID:
        job = self.job
        run = self.runner.client.create_search_run(
            job.bundle.experiment_id,
            SearchRunCreate(
                lease_id=job.lease.lease_id,
                attack_spec_id=attack_spec_id,
                level=level,
                scope=scope,
                search_order=order,
            ),
        )
        if (run.attack_spec_id, run.level, run.scope, run.search_order) != (
            attack_spec_id,
            level,
            scope,
            order,
        ):
            raise ValueError(f"API tạo run {run.run_id} không khớp điểm đã yêu cầu")
        job.runs[run.run_id] = run
        job.ledger.add(run)
        return run.run_id

    def execute(self, run_id: UUID) -> PointOutcome:
        job = self.job
        run = job.runs[run_id]
        try:
            self.runner._run_one(job, run_id, self.spec, self.runner._inputs(job, run, self.spec))
        except _StopExperiment:
            outcome = job.outcomes.get(run_id, PointOutcome(RunStatus.CANCELLED, None))
            return PointOutcome(outcome.status, outcome.metrics, outcome.message, stop=True)
        return job.outcomes[run_id]

    def report(self, result: SearchResult) -> None:
        self.runner.client.search_result(
            self.job.bundle.experiment_id,
            SearchResultReport(lease_id=self.job.lease.lease_id, result=result),
        )

    def predictions(self, run_id: UUID) -> dict[str, Prediction] | None:
        """Prediction của run hoàn tất trong phiên này (bộ nhớ); run đã kết thúc ở phiên trước
        hoặc trúng cache thì đọc `runs/<run_id>/predictions.json` qua `artifact-url` của chính run
        (đề xuất contract 001, plan task 18b). Không có file → `None` (bỏ khỏi bootstrap)."""
        cached = self.job.predictions.get(run_id)
        if cached is not None:
            return cached
        runner, lease_id = self.runner, self.job.lease.lease_id
        store = PresignedStore(
            lambda key, method: runner.client.artifact_url(run_id, lease_id, key, method),
            runner.url_http,
        )
        try:
            data = store.get(run_predictions_key(run_id))
        except KeyNotFoundError:
            logger.warning("Run %s không có file prediction", run_id)
            return None
        return read_predictions_file(data)


def read_predictions_file(data: bytes) -> dict[str, Prediction]:
    """File prediction của một run. Bản sao do API tạo khi trúng cache giữ khóa của run gốc trong
    trường `key`: đọc theo đúng run ghi trong file (vẫn kiểm file nhất quán với khóa của nó)."""
    key = json.loads(data).get("key")
    match = _PREDICTIONS_KEY.fullmatch(key) if isinstance(key, str) else None
    if match is None:
        raise ValueError(f"File prediction có khóa không hợp lệ: {key!r}")
    return load_run_predictions(data, UUID(match.group(1)))
