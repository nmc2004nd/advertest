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

Phase R1 (`### Điều phối`): `JobRunner` chỉ giữ lease, heartbeat, thứ tự run, directive và lời
gọi API của experiment. Chạy một run nằm ở `pipeline.RunPipeline`, hoàn tất run ở
`finish.RunFinisher`, patch ở `patch.patch_perturbation`, dừng sớm ở `early_stop`, hook tìm
ngưỡng ở `search_hooks`, calibration ở `calibrate.calibrate_bundle`.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

import httpx

from advertest_contracts.enums import RunMode, RunStatus
from advertest_contracts.models import AttackConfig, CostProfile, WorkerJobBundle, WorkerLease
from advertest_worker.cache import JobCache
from advertest_worker.calibrate import calibrate_bundle
from advertest_worker.client import LeaseLost, WorkerClient
from advertest_worker.config import HEARTBEAT_INTERVAL_S
from advertest_worker.early_stop import RunLedger, skip_early_stop
from advertest_worker.errors import StopExperiment
from advertest_worker.pipeline import BatchHook, RunPipeline
from advertest_worker.search import KnownRun, SearchDriver
from advertest_worker.search_hooks import JobSearchHooks
from advertest_worker.state import DirectiveBox, JobState
from attacks.builders import DEFAULT_REGISTRY, PerturbationRegistry
from ml_core.models.adapter import ModelProvider
from ml_core.runner.cache_loader import ShaCacheLoader
from ml_core.runner.fingerprint import FingerprintService
from ml_core.runner.manifest import ManifestBuilder
from ml_core.runner.perturbations import ModelSource, PerturbationFactory, registry_factory
from ml_core.runner.provenance import EnvProvenance, Provenance

__all__ = ["BatchHook", "DirectiveBox", "Heartbeat", "JobRunner", "PerturbationFactory"]

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------- heartbeat


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
        perturbation_factory: PerturbationFactory | None = None,
        provenance: Provenance | None = None,
        registry: PerturbationRegistry = DEFAULT_REGISTRY,
        model_provider: ModelSource | None = None,
    ) -> None:
        self.client = client
        self.cache = cache
        self.url_http = url_http or httpx.Client(timeout=120.0)
        self.heartbeat_interval_s = heartbeat_interval_s
        self.clock = clock
        self.provenance = provenance or EnvProvenance()
        self.pipeline = RunPipeline(
            client,
            cache,
            device,
            url_http=self.url_http,
            clock=clock,
            on_batch=on_batch,
            registry=registry,
            perturbation_factory=perturbation_factory or registry_factory(registry),
            models=model_provider or ModelProvider(cache.store),
        )

    def calibrate_bundle(
        self, bundle: WorkerJobBundle, loader: ShaCacheLoader, *, force: bool = False
    ) -> dict[UUID, CostProfile]:
        """Cost profile cho mọi attack của bundle (`calibrate.calibrate_bundle`)."""
        return calibrate_bundle(self.pipeline, bundle, loader, force=force)

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
        job = JobState(
            lease=lease,
            bundle=bundle,
            loader=loader,
            box=box,
            environment=self.pipeline.environment(bundle),
            profiles=self.calibrate_bundle(bundle, loader),
            specs={s.id: s for s in bundle.attack_specs},
            remaining_seconds=(float(limit.value - limit.used) if limit.kind == "time" else None),
            ledger=RunLedger(bundle),
            runs={run.run_id: run for run in bundle.runs},
        )
        # Provenance đọc một lần mỗi experiment, ở run đầu tiên cần fingerprint.
        job.fingerprints = FingerprintService(
            self.provenance,
            params=bundle.inference_params,
            mapping=bundle.class_mapping,
            slice_spec=bundle.slice,
            weights_sha256=bundle.model_card.weights_sha256,
        )
        job.manifests = ManifestBuilder(lambda: job.environment, self.clock)
        for run in bundle.runs:
            if run.search_order is not None:
                continue  # run tìm ngưỡng chạy trong vòng lặp tìm kiếm (Phase 7)
            if run.status not in (RunStatus.QUEUED, RunStatus.RUNNING):
                continue
            if self._directive_stops(job):
                return
            spec = job.specs[run.attack_spec_id]
            if skip_early_stop(
                self.client, job.ledger, lease.lease_id, run.run_id, spec.name, run.level
            ):
                continue
            try:
                self.pipeline.run(job, run.run_id, spec)
            except StopExperiment:
                return
        for attack in bundle.config.attacks:
            if attack.mode != RunMode.SEARCH:
                continue
            if self._directive_stops(job):
                return
            if self._search(job, attack):
                return

    @staticmethod
    def _directive_stops(job: JobState) -> bool:
        directive = job.box.current()
        if directive is not None and directive.action != "continue":
            logger.info("Dừng experiment theo chỉ thị %s", directive.action)
            return True
        return False

    # ------------------------------------------------------------------ tìm ngưỡng (Phase 7)

    def _search(self, job: JobState, attack: AttackConfig) -> bool:
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
            context=self.pipeline.context(job),
            hooks=JobSearchHooks(self.client, self.url_http, self.pipeline.run, job, attack, spec),
            known_runs=known,
            previous=previous,
        )
        logger.info("[%s] tìm ngưỡng", spec.name)
        return driver.run()
