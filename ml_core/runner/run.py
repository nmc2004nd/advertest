"""Chạy quét lưới attack theo `LocalRunConfig` (requirements.md Phase 2, plan.md task 21-24).

Mỗi cặp (attack, level) là một run:
cache theo fingerprint → kiểm tra tương thích → attack theo batch (mask từ letterbox) → predict →
metric → chọn failure case → ghi artifact, manifest và `RunResult`.

Bố cục trong store (bất biến):
- `runs/<fp>/`: kết quả `completed` đầu tiên của fingerprint (`manifest.json`, `result.json`,
  `cases/<image_id>/{clean,adversarial,perturbation}.png`, `cases/<image_id>/record.json`);
- `runs/<fp>/reruns/<run_id>/`: chạy lại bằng `--force` khi đã có kết quả;
- `runs/<fp>/attempts/<run_id>/`: run `failed` hoặc `skipped` (`incompatible`).
Run `skipped` (`cached`) chỉ được trả về, không ghi vào store.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from advertest_contracts.enums import RunStatus, SkipReason
from advertest_contracts.models import (
    AttackSpec,
    EvalMetrics,
    FingerprintInputs,
    InferenceParams,
    Manifest,
    Progress,
    RunResult,
    StatusReason,
)
from advertest_contracts.perturbation import Perturbation
from attacks.art_adapter import IncompatibleAttack
from attacks.factory import build_perturbation
from ml_core.cli.cache import Prediction
from ml_core.cli.evaluate import load_model_from_store, predict_slice
from ml_core.data.loader import SliceLoader
from ml_core.models.estimator import build_estimator
from ml_core.models.register import lib_versions
from ml_core.models.wrapper import DEFAULT_INFERENCE_PARAMS
from ml_core.runner.candidates import MemoryCandidates
from ml_core.runner.config import LocalRunConfig, experiment_id, resolve_specs
from ml_core.runner.env import (
    default_device,
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
from ml_core.runner.images import amplified_perturbation, letterbox_mask, perturbation_kind
from ml_core.store import ArtifactStore

__all__ = ["amplified_perturbation", "letterbox_mask"]

PerturbationFactory = Callable[[AttackSpec, Any], Perturbation]
ProgressFn = Callable[[str], None]


def run_prefix(fp: str) -> str:
    return f"runs/{fp}"


def result_key(prefix: str) -> str:
    return f"{prefix}/result.json"


def manifest_key(prefix: str) -> str:
    return f"{prefix}/manifest.json"


@dataclass(frozen=True)
class RunOutcome:
    result: RunResult
    spec_name: str
    prefix: str | None  # thư mục trong store; None với run cached (không ghi gì)


@dataclass
class RunReport:
    experiment_id: UUID
    git_dirty: bool
    clean: EvalMetrics
    outcomes: list[RunOutcome] = field(default_factory=list)


class Runner:
    def __init__(
        self,
        store: ArtifactStore,
        config: LocalRunConfig,
        *,
        force: bool = False,
        progress: ProgressFn | None = None,
        perturbation_factory: PerturbationFactory = build_perturbation,
        params: InferenceParams = DEFAULT_INFERENCE_PARAMS,
    ) -> None:
        self.store = store
        self.config = config
        self.force = force
        self.progress = progress or (lambda _message: None)
        self.perturbation_factory = perturbation_factory
        self.params = params
        self.device = config.device or default_device()
        self.specs = resolve_specs(config)
        self.git = git_state()
        self.versions = lib_versions()
        self.docker_digest = docker_image_digest()
        self.experiment_id = experiment_id(config)

        self.loader = SliceLoader.from_ids(store, config.slice_id, config.mapping_id)
        self.card = self.loader.card
        if self.card.id != config.model_id:
            raise ValueError(
                f"Mapping {config.mapping_id} thuộc model {self.card.id}, không phải "
                f"{config.model_id}"
            )
        self.slice = self.loader.slice
        self.mapping = self.loader.mapping
        self._estimator: Any = None

    # ------------------------------------------------------------------ chuẩn bị

    @property
    def estimator(self) -> Any:
        """Nạp model khi cần lần đầu (không nạp nếu mọi run đều cached và cache sạch có sẵn)."""
        if self._estimator is None:
            model = load_model_from_store(self.store, self.card.weights_sha256)
            self._estimator = build_estimator(model, self.params, self.device)
        return self._estimator

    def clean_predictions(self) -> dict[str, Prediction]:
        """Prediction thô trên ảnh sạch từ cache của Phase 1; chưa có thì chạy như `eval`."""
        return load_clean_predictions(
            self.store,
            self.loader,
            self.params,
            lambda: self.estimator,
            self.config.batch_size,
            lambda: describe_device(self.device),
            self.progress,
            # Tra `predict_slice` lúc gọi: test thay hàm này để kiểm tra đã dùng cache.
            lambda loader, estimator, batch_size: predict_slice(loader, estimator, batch_size),
        )

    # ------------------------------------------------------------------ chạy

    def run(self) -> RunReport:
        context = build_context(
            self.loader, self.clean_predictions(), self.params, self.config.failure_cases_per_run
        )
        report = RunReport(
            experiment_id=self.experiment_id, git_dirty=self.git.dirty, clean=context.clean_metrics
        )
        for attack, spec in zip(self.config.attacks, self.specs, strict=True):
            assert attack.grid is not None  # LocalRunConfig chỉ nhận mode = grid
            for level in attack.grid.levels:
                outcome = self._run_one(spec, float(level), attack.seed, context)
                report.outcomes.append(outcome)
        return report

    def _fingerprint_inputs(self, spec: AttackSpec, level: float, seed: int) -> FingerprintInputs:
        return build_fingerprint_inputs(
            spec=spec,
            level=level,
            seed=seed,
            params=self.params,
            mapping=self.mapping,
            slice_spec=self.slice,
            weights_sha256=self.card.weights_sha256,
            git_commit=self.git.commit,
            git_dirty=self.git.dirty,
            lib_versions=self.versions,
            docker_image_digest=self.docker_digest,
        )

    def _result(
        self,
        run_id: UUID,
        fp: str,
        spec: AttackSpec,
        level: float,
        status: RunStatus,
        **fields: Any,
    ) -> RunResult:
        fields.setdefault(
            "progress", Progress(images_done=0, images_total=len(self.slice.image_ids))
        )
        fields.setdefault("gpu_seconds", 0.0)
        fields.setdefault("failure_case_ids", [])
        return RunResult(
            run_id=run_id,
            experiment_id=self.experiment_id,
            fingerprint=fp,
            attack_spec_id=spec.id,
            level=level,
            status=status,
            cost=None,
            **fields,
        )

    def _write_manifest(self, prefix: str, run_id: UUID, inputs: FingerprintInputs) -> str:
        manifest = Manifest(
            run_id=run_id,
            fingerprint=fingerprint(inputs),
            fingerprint_inputs=inputs,
            environment=environment(self.device),
            created_at=datetime.now(UTC),
        )
        key = manifest_key(prefix)
        self.store.put(key, (manifest.model_dump_json(indent=2) + "\n").encode())
        return key

    def _write_result(self, prefix: str, result: RunResult) -> None:
        self.store.put(result_key(prefix), (result.model_dump_json(indent=2) + "\n").encode())

    def _run_one(
        self,
        spec: AttackSpec,
        level: float,
        seed: int,
        context: RunContext,
    ) -> RunOutcome:
        inputs = self._fingerprint_inputs(spec, level, seed)
        fp = fingerprint(inputs)
        base = run_prefix(fp)
        has_result = self.store.exists(result_key(base))

        if has_result and not self.force:
            previous = RunResult.model_validate_json(self.store.get(result_key(base)))
            self.progress(f"[{spec.name} {level:g}] cached ({fp[:12]})")
            result = self._result(
                uuid4(),
                fp,
                spec,
                level,
                RunStatus.SKIPPED,
                status_reason=StatusReason(
                    code=SkipReason.CACHED,
                    message=f"Đã có kết quả completed (run {previous.run_id})",
                ),
                progress=previous.progress,
                metrics=previous.metrics,
                failure_case_ids=previous.failure_case_ids,
                manifest_uri=previous.manifest_uri,
            )
            return RunOutcome(result=result, spec_name=spec.name, prefix=None)

        run_id = uuid4()
        attempt = f"{base}/attempts/{run_id}"
        perturbation: Perturbation | None = None
        reason: str | None = None
        if spec.requires_gradients and not self.card.supports_gradients:
            reason = f"{spec.name} cần gradient nhưng model {self.card.name} không hỗ trợ gradient"
        else:
            try:
                perturbation = self.perturbation_factory(spec, self.estimator)
            except IncompatibleAttack as exc:
                reason = str(exc)
            except Exception as exc:  # lỗi khi dựng attack: run này failed, các run khác chạy tiếp
                return self._failed(spec, level, run_id, fp, inputs, attempt, exc, _Execution())
        if perturbation is None:
            self.progress(f"[{spec.name} {level:g}] skipped: {reason}")
            manifest_uri = self._write_manifest(attempt, run_id, inputs)
            result = self._result(
                run_id,
                fp,
                spec,
                level,
                RunStatus.SKIPPED,
                status_reason=StatusReason(code=SkipReason.INCOMPATIBLE, message=reason or "-"),
                manifest_uri=manifest_uri,
            )
            self._write_result(attempt, result)
            return RunOutcome(result=result, spec_name=spec.name, prefix=attempt)

        prefix = f"{base}/reruns/{run_id}" if has_result else base
        state = _Execution()
        try:
            result = self._execute(
                perturbation,
                spec,
                level,
                seed,
                run_id,
                fp,
                inputs,
                prefix,
                context,
                state,
            )
        except Exception as exc:  # một run lỗi không dừng các run khác (requirements.md, CLI)
            return self._failed(spec, level, run_id, fp, inputs, attempt, exc, state)
        return RunOutcome(result=result, spec_name=spec.name, prefix=prefix)

    def _failed(
        self,
        spec: AttackSpec,
        level: float,
        run_id: UUID,
        fp: str,
        inputs: FingerprintInputs,
        attempt: str,
        exc: Exception,
        state: _Execution,
    ) -> RunOutcome:
        message = f"{type(exc).__name__}: {exc}"
        self.progress(f"[{spec.name} {level:g}] failed: {message}")
        manifest_uri = self._write_manifest(attempt, run_id, inputs)
        result = self._result(
            run_id,
            fp,
            spec,
            level,
            RunStatus.FAILED,
            status_reason=StatusReason(code="error", message=message),
            progress=Progress(
                images_done=state.images_done, images_total=len(self.slice.image_ids)
            ),
            gpu_seconds=state.device_seconds,
            manifest_uri=manifest_uri,
        )
        self._write_result(attempt, result)
        return RunOutcome(result=result, spec_name=spec.name, prefix=attempt)

    def _execute(
        self,
        perturbation: Perturbation,
        spec: AttackSpec,
        level: float,
        seed: int,
        run_id: UUID,
        fp: str,
        inputs: FingerprintInputs,
        prefix: str,
        context: RunContext,
        state: _Execution,
    ) -> RunResult:
        total = len(self.slice.image_ids)
        executor = RunExecutor(
            fingerprint=fp,
            level=level,
            seed=seed,
            perturbation=perturbation,
            estimator=self.estimator,
            context=context,
            candidates=MemoryCandidates(
                self.store,
                prefix,
                linf_eps(spec, perturbation, level),
                perturbation_kind(spec),
            ),
        )
        for batch in executor.batches(self.loader, self.config.batch_size):
            executor.process_batch(batch)
            state.images_done = executor.images_done
            state.device_seconds = executor.processing_seconds
            self.progress(f"[{spec.name} {level:g}] {state.images_done}/{total} ảnh")

        finalized = executor.finalize(run_id)
        for record in finalized.failure_cases:
            key = f"{prefix}/cases/{record.image_id}/record.json"
            self.store.put(key, (record.model_dump_json(indent=2) + "\n").encode())
        manifest_uri = self._write_manifest(prefix, run_id, inputs)
        result = self._result(
            run_id,
            fp,
            spec,
            level,
            RunStatus.COMPLETED,
            progress=Progress(images_done=total, images_total=total),
            metrics=finalized.metrics,
            gpu_seconds=executor.processing_seconds,
            failure_case_ids=[record.id for record in finalized.failure_cases],
            manifest_uri=manifest_uri,
        )
        # result.json ghi sau cùng: có result.json nghĩa là run đã ghi đủ artifact.
        self._write_result(prefix, result)
        return result


@dataclass
class _Execution:
    images_done: int = 0
    device_seconds: float = 0.0


def run_config(
    store: ArtifactStore,
    config: LocalRunConfig,
    *,
    force: bool = False,
    progress: ProgressFn | None = None,
    perturbation_factory: PerturbationFactory = build_perturbation,
) -> RunReport:
    runner = Runner(
        store, config, force=force, progress=progress, perturbation_factory=perturbation_factory
    )
    return runner.run()
