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

import io
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from advertest_contracts.enums import RunStatus, SkipReason
from advertest_contracts.models import (
    AttackSpec,
    CaseArtifacts,
    CaseBox,
    CaseDetections,
    CaseIgnoreRegion,
    EvalMetrics,
    FailureCaseRecord,
    FingerprintInputs,
    InferenceParams,
    Manifest,
    Progress,
    RunResult,
    StatusReason,
    compute_failure_case_id,
)
from attacks.art_adapter import ArtPerturbation, IncompatibleAttack, build_perturbation
from ml_core.cli.cache import Prediction, load_predictions, prediction_cache_key, save_predictions
from ml_core.cli.evaluate import ground_truth, load_model_from_store, predict_slice
from ml_core.data.loader import SliceLoader
from ml_core.metrics.attack import (
    ImageAttackStats,
    build_run_metrics,
    image_attack_stats,
    select_failure_cases,
)
from ml_core.metrics.clean import CleanMetric
from ml_core.metrics.filters import filter_classes, filter_ignored
from ml_core.models.estimator import build_estimator
from ml_core.models.register import lib_versions
from ml_core.models.wrapper import DEFAULT_INFERENCE_PARAMS
from ml_core.preprocess import LetterboxInfo
from ml_core.runner.config import LocalRunConfig, experiment_id, resolve_specs
from ml_core.runner.env import (
    default_device,
    describe_device,
    docker_image_digest,
    environment,
    git_state,
)
from ml_core.runner.fingerprint import build_fingerprint_inputs, fingerprint
from ml_core.store import ArtifactStore

PerturbationFactory = Callable[[AttackSpec, Any], ArtPerturbation]
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


def letterbox_mask(infos: Sequence[LetterboxInfo]) -> NDArray[np.float32]:
    """(N, 1, size, size): 1 ở vùng ảnh thật, 0 ở vùng pad (cùng hình học với `letterbox`)."""
    size = infos[0].size
    mask = np.zeros((len(infos), 1, size, size), dtype=np.float32)
    for i, info in enumerate(infos):
        width, height = info.orig_size
        new_w = max(1, min(size, round(width * info.scale)))
        new_h = max(1, min(size, round(height * info.scale)))
        left, top = info.pad
        mask[i, :, top : top + new_h, left : left + new_w] = 1.0
    return mask


def _bbox(box: NDArray[Any]) -> tuple[float, float, float, float]:
    x1, y1, x2, y2 = (float(v) for v in np.asarray(box).reshape(4))
    return x1, y1, x2, y2


def _png(image: NDArray[np.float32]) -> bytes:
    """(C, H, W) trong [0, 1] → PNG RGB 8-bit (chỉ để hiển thị)."""
    pixels = np.round(np.clip(image, 0.0, 1.0) * 255).astype(np.uint8).transpose(1, 2, 0)
    buffer = io.BytesIO()
    Image.fromarray(pixels).save(buffer, format="PNG")
    return buffer.getvalue()


def amplified_perturbation(
    clean: NDArray[np.float32], adversarial: NDArray[np.float32], linf_eps: float | None
) -> NDArray[np.float32]:
    """Ảnh nhiễu khuếch đại: `0.5 + δ / (2·eps)` với L∞; `0.5 + δ / (2·max|δ|)` với L2
    (`linf_eps = None`), δ = 0 thì toàn ảnh 0.5; cắt về [0, 1]."""
    delta = adversarial.astype(np.float64) - clean.astype(np.float64)
    scale = linf_eps if linf_eps is not None else float(np.abs(delta).max())
    if scale <= 0:
        return np.full(clean.shape, 0.5, dtype=np.float32)
    return np.clip(0.5 + delta / (2 * scale), 0.0, 1.0).astype(np.float32)


@dataclass(frozen=True)
class _Candidate:
    stats: ImageAttackStats
    clean: NDArray[np.float32]
    adversarial: NDArray[np.float32]
    attacked_pred: Prediction
    target: dict[str, NDArray[Any]]
    ignore: dict[str, Any]


class _TopCases:
    """Giữ tối đa `limit` ảnh theo đúng quy tắc của `select_failure_cases`, để không phải giữ
    ảnh của cả slice trong bộ nhớ."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.items: dict[str, _Candidate] = {}

    def offer(self, image_id: str, candidate: _Candidate) -> None:
        if self.limit == 0 or candidate.stats.severity_score <= 0:
            return
        self.items[image_id] = candidate
        keep = select_failure_cases({k: v.stats for k, v in self.items.items()}, self.limit)
        self.items = {k: self.items[k] for k, _ in keep}
        if image_id in self.items:
            # Ảnh là view của mảng cả batch: chép riêng để không giữ cả batch trong bộ nhớ.
            self.items[image_id] = replace(
                candidate, clean=candidate.clean.copy(), adversarial=candidate.adversarial.copy()
            )


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
        target_classes = {c for c in self.mapping.classes.values() if c is not None}
        self.target_classes = target_classes
        self.target_labels = sorted(self.card.class_names.index(c) for c in target_classes)
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
        key = prediction_cache_key(self.card.weights_sha256, self.slice, self.params)
        cached = load_predictions(self.store, key)
        if cached is not None:
            predictions = cached.predictions
        else:
            self.progress("Chưa có cache prediction ảnh sạch: chạy predict trên slice")
            predictions = predict_slice(self.loader, self.estimator, self.config.batch_size)
            save_predictions(self.store, key, predictions, describe_device(self.device))
        missing = [i for i in self.slice.image_ids if i not in predictions]
        if missing:
            raise ValueError(f"Cache thiếu prediction của {len(missing)} ảnh, ví dụ {missing[:3]}")
        return predictions

    def _new_metric(self) -> CleanMetric:
        return CleanMetric(self.card.class_names, self.target_classes, self.params.max_det)

    # ------------------------------------------------------------------ chạy

    def run(self) -> RunReport:
        clean_preds = self.clean_predictions()
        targets, ignores = ground_truth(self.loader)
        ids = self.slice.image_ids
        clean_metric = self._new_metric()
        clean_metric.update(
            [clean_preds[i] for i in ids], [targets[i] for i in ids], [ignores[i] for i in ids]
        )
        report = RunReport(
            experiment_id=self.experiment_id, git_dirty=self.git.dirty, clean=clean_metric.compute()
        )
        for attack, spec in zip(self.config.attacks, self.specs, strict=True):
            assert attack.grid is not None  # LocalRunConfig chỉ nhận mode = grid
            for level in attack.grid.levels:
                outcome = self._run_one(spec, float(level), attack.seed, clean_preds, report.clean)
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
        clean_preds: dict[str, Prediction],
        clean: EvalMetrics,
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
        perturbation: ArtPerturbation | None = None
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
                clean_preds,
                clean,
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
        perturbation: ArtPerturbation,
        spec: AttackSpec,
        level: float,
        seed: int,
        run_id: UUID,
        fp: str,
        inputs: FingerprintInputs,
        prefix: str,
        clean_preds: dict[str, Prediction],
        clean: EvalMetrics,
        state: _Execution,
    ) -> RunResult:
        total = len(self.slice.image_ids)
        metric = self._new_metric()
        stats: dict[str, ImageAttackStats] = {}
        top = _TopCases(self.config.failure_cases_per_run)
        conf = self.params.operating_conf

        for batch in self.loader.batches(self.config.batch_size):
            start = time.perf_counter()
            mask = letterbox_mask(batch.infos)
            adversarial = perturbation.apply(batch.images, batch.targets, level, seed, mask)
            preds = self.estimator.predict(adversarial, batch_size=self.config.batch_size)
            state.device_seconds += time.perf_counter() - start

            ignore_boxes = [item["boxes"] for item in batch.ignore]
            metric.update(preds, batch.targets, ignore_boxes)
            for i, image_id in enumerate(batch.image_ids):
                s = image_attack_stats(
                    clean_preds[image_id],
                    preds[i],
                    batch.targets[i],
                    ignore_boxes[i],
                    self.target_labels,
                    conf,
                )
                stats[image_id] = s
                top.offer(
                    image_id,
                    _Candidate(
                        stats=s,
                        clean=batch.images[i],
                        adversarial=adversarial[i],
                        attacked_pred=preds[i],
                        target=batch.targets[i],
                        ignore=batch.ignore[i],
                    ),
                )
            state.images_done += len(batch.image_ids)
            self.progress(f"[{spec.name} {level:g}] {state.images_done}/{total} ảnh")

        metrics = build_run_metrics(clean, metric.compute(), stats.values())
        selected = select_failure_cases(stats, self.config.failure_cases_per_run)
        if [image_id for image_id, _ in selected] != list(top.items):
            raise RuntimeError("Failure case giữ trong lúc chạy lệch với select_failure_cases")

        linf = str(spec.fixed_params.get("norm")) == "inf"
        linf_eps = perturbation.eps(level) if linf else None
        case_ids = [
            self._write_case(
                prefix, run_id, fp, image_id, top.items[image_id], clean_preds[image_id], linf_eps
            )
            for image_id, _ in selected
        ]
        manifest_uri = self._write_manifest(prefix, run_id, inputs)
        result = self._result(
            run_id,
            fp,
            spec,
            level,
            RunStatus.COMPLETED,
            progress=Progress(images_done=total, images_total=total),
            metrics=metrics,
            gpu_seconds=state.device_seconds,
            failure_case_ids=case_ids,
            manifest_uri=manifest_uri,
        )
        # result.json ghi sau cùng: có result.json nghĩa là run đã ghi đủ artifact.
        self._write_result(prefix, result)
        return result

    # ------------------------------------------------------------------ failure case

    def _boxes(self, pred: Prediction, ignore: NDArray[Any]) -> list[CaseBox]:
        kept = filter_ignored(filter_classes(pred, self.target_labels), ignore)
        confident = kept["scores"] >= self.params.operating_conf
        return [
            CaseBox(
                bbox=_bbox(box),
                class_name=self.card.class_names[int(label)],
                score=float(score),
            )
            for box, label, score in zip(
                kept["boxes"][confident],
                kept["labels"][confident],
                kept["scores"][confident],
                strict=True,
            )
        ]

    def _write_case(
        self,
        prefix: str,
        run_id: UUID,
        fp: str,
        image_id: str,
        case: _Candidate,
        clean_pred: Prediction,
        linf_eps: float | None,
    ) -> UUID:
        base = f"{prefix}/cases/{image_id}"
        artifacts = CaseArtifacts(
            clean_png=f"{base}/clean.png",
            adversarial_png=f"{base}/adversarial.png",
            perturbation_png=f"{base}/perturbation.png",
        )
        self.store.put(artifacts.clean_png, _png(case.clean))
        self.store.put(artifacts.adversarial_png, _png(case.adversarial))
        self.store.put(
            artifacts.perturbation_png,
            _png(amplified_perturbation(case.clean, case.adversarial, linf_eps)),
        )
        ignore_boxes = np.asarray(case.ignore["boxes"]).reshape(-1, 4)
        detections = CaseDetections(
            ground_truth=[
                CaseBox(
                    bbox=_bbox(box),
                    class_name=self.card.class_names[int(label)],
                    score=None,
                )
                for box, label in zip(
                    np.asarray(case.target["boxes"]).reshape(-1, 4),
                    case.target["labels"],
                    strict=True,
                )
            ],
            clean=self._boxes(clean_pred, ignore_boxes),
            attacked=self._boxes(case.attacked_pred, ignore_boxes),
            ignore_regions=[
                CaseIgnoreRegion(bbox=_bbox(box), source=source)
                for box, source in zip(ignore_boxes, case.ignore["sources"], strict=True)
            ],
        )
        record = FailureCaseRecord(
            id=compute_failure_case_id(fp, image_id),
            run_id=run_id,
            fingerprint=fp,
            image_id=image_id,
            lost_objects=case.stats.lost,
            new_false_positives=case.stats.new_false_positives,
            severity_score=case.stats.severity_score,
            detections=detections,
            artifacts=artifacts,
        )
        self.store.put(f"{base}/record.json", (record.model_dump_json(indent=2) + "\n").encode())
        return record.id


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
