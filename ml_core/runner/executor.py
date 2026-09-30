"""Chạy một run theo từng batch, trạng thái lưu được (requirements.md Phase 3, Executor dùng chung).

`RunExecutor` dùng chung cho CLI `advertest run` và worker:

1. dựng với attack đã sẵn sàng, bối cảnh của slice (`RunContext`) và nơi nhận ảnh ứng viên;
2. `process_batch(batch)` cho từng batch (attack có mask letterbox → predict → thống kê ảnh →
   cập nhật top-K ứng viên);
3. `finalize(run_id, partial=...)` tính `RunMetrics` và dựng `FailureCaseRecord`.

Sau mỗi batch, `to_checkpoint()` trả JSON đủ để `from_checkpoint()` chạy tiếp từ ảnh chưa xử lý:
prediction sau tấn công **đã lọc class đích**, `ImageAttackStats` từng ảnh, khóa ứng viên. Không
chứa ảnh. mAP luôn được tính lại ở `finalize` từ prediction đã lưu, theo thứ tự ảnh của slice,
nên chạy liền mạch và chạy tiếp cho cùng kết quả; mỗi ảnh được tính đúng một lần.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import numpy as np
from numpy.typing import NDArray

from advertest_contracts.models import (
    AttackSpec,
    CaseBox,
    CaseDetections,
    CaseIgnoreRegion,
    EvalMetrics,
    FailureCaseRecord,
    InferenceParams,
    RunMetrics,
    compute_failure_case_id,
)
from advertest_contracts.perturbation import Perturbation
from attacks.art_adapter import ArtPerturbation
from ml_core.cli.cache import Prediction, load_predictions, prediction_cache_key, save_predictions
from ml_core.cli.evaluate import ground_truth, predict_slice
from ml_core.data.loader import Batch, SliceLoader
from ml_core.metrics.attack import (
    ImageAttackStats,
    build_run_metrics,
    image_attack_stats,
    select_failure_cases,
)
from ml_core.metrics.clean import CleanMetric
from ml_core.metrics.filters import filter_classes, filter_ignored
from ml_core.privacy.case import anonymization, case_regions
from ml_core.runner.candidates import CandidateSink
from ml_core.runner.images import bbox, letterbox_mask
from ml_core.store import ArtifactStore

CHECKPOINT_VERSION = 1


class CheckpointMismatchError(ValueError):
    """Checkpoint thuộc run khác (fingerprint hoặc slice khác)."""


# ---------------------------------------------------------------- bối cảnh của slice


@dataclass(frozen=True)
class RunContext:
    """Dữ liệu chung cho mọi run của một experiment (cùng model, slice, mapping)."""

    image_ids: list[str]  # theo thứ tự của slice
    class_names: list[str]
    target_classes: frozenset[str]
    target_labels: list[int]
    params: InferenceParams
    clean_predictions: dict[str, Prediction]  # prediction thô trên ảnh sạch
    targets: dict[str, dict[str, NDArray[Any]]]  # ground truth, box letterbox
    ignore_boxes: dict[str, NDArray[np.float32]]
    clean_metrics: EvalMetrics  # mAP sạch trên cả slice
    failure_cases_per_run: int

    def new_metric(self) -> CleanMetric:
        return CleanMetric(self.class_names, self.target_classes, self.params.max_det)

    def clean_metrics_on(self, image_ids: Sequence[str]) -> EvalMetrics:
        metric = self.new_metric()
        metric.update(
            [self.clean_predictions[i] for i in image_ids],
            [self.targets[i] for i in image_ids],
            [self.ignore_boxes[i] for i in image_ids],
        )
        return metric.compute()


def build_context(
    loader: SliceLoader,
    clean_predictions: dict[str, Prediction],
    params: InferenceParams,
    failure_cases_per_run: int,
) -> RunContext:
    missing = [i for i in loader.slice.image_ids if i not in clean_predictions]
    if missing:
        raise ValueError(f"Thiếu prediction ảnh sạch của {len(missing)} ảnh, ví dụ {missing[:3]}")
    target_classes = frozenset(c for c in loader.mapping.classes.values() if c is not None)
    class_names = list(loader.card.class_names)
    targets, ignores = ground_truth(loader)
    image_ids = list(loader.slice.image_ids)
    clean = CleanMetric(class_names, target_classes, params.max_det)
    clean.update(
        [clean_predictions[i] for i in image_ids],
        [targets[i] for i in image_ids],
        [ignores[i] for i in image_ids],
    )
    return RunContext(
        image_ids=image_ids,
        class_names=class_names,
        target_classes=target_classes,
        target_labels=sorted(class_names.index(c) for c in target_classes),
        params=params,
        clean_predictions=clean_predictions,
        targets=targets,
        ignore_boxes=ignores,
        clean_metrics=clean.compute(),
        failure_cases_per_run=failure_cases_per_run,
    )


def load_clean_predictions(
    store: ArtifactStore,
    loader: SliceLoader,
    params: InferenceParams,
    estimator: Callable[[], Any],
    batch_size: int,
    device_description: Callable[[], str],
    progress: Callable[[str], None] = lambda _message: None,
    predict: Callable[[SliceLoader, Any, int], dict[str, Prediction]] = predict_slice,
) -> dict[str, Prediction]:
    """Prediction thô trên ảnh sạch từ cache theo (model, slice) của Phase 1; chưa có thì chạy
    predict như `advertest eval` rồi ghi cache. `estimator` chỉ được gọi khi cache chưa có."""
    key = prediction_cache_key(loader.card.weights_sha256, loader.slice, params)
    cached = load_predictions(store, key)
    if cached is not None:
        return cached.predictions
    progress("Chưa có cache prediction ảnh sạch: chạy predict trên slice")
    predictions = predict(loader, estimator(), batch_size)
    save_predictions(store, key, predictions, device_description())
    return predictions


# ---------------------------------------------------------------- tuần tự hóa


def _pred_to_json(pred: Prediction) -> dict[str, Any]:
    return {
        "boxes": np.asarray(pred["boxes"], dtype=np.float32).reshape(-1, 4).tolist(),
        "labels": np.asarray(pred["labels"], dtype=np.int64).tolist(),
        "scores": np.asarray(pred["scores"], dtype=np.float32).tolist(),
    }


def _pred_from_json(data: dict[str, Any]) -> Prediction:
    return {
        "boxes": np.asarray(data["boxes"], dtype=np.float32).reshape(-1, 4),
        "labels": np.asarray(data["labels"], dtype=np.int64),
        "scores": np.asarray(data["scores"], dtype=np.float32),
    }


def _stats_to_json(stats: ImageAttackStats) -> dict[str, int]:
    return {
        "correct": stats.correct,
        "lost": stats.lost,
        "clean_fp": stats.clean_fp,
        "attacked_fp": stats.attacked_fp,
    }


# ---------------------------------------------------------------- executor


@dataclass(frozen=True)
class FinalizedRun:
    metrics: RunMetrics
    failure_cases: list[FailureCaseRecord]
    images_done: int


def linf_eps(spec: AttackSpec, perturbation: Perturbation, level: float) -> float | None:
    """eps trên ảnh [0, 1] của attack ART L∞ (để khuếch đại ảnh nhiễu); `None` với chuẩn khác và
    với phép biến đổi không phải attack ART (corruption, occlusion, patch)."""
    if not isinstance(perturbation, ArtPerturbation):
        return None
    return perturbation.eps(level) if str(spec.fixed_params.get("norm")) == "inf" else None


class RunExecutor:
    def __init__(
        self,
        *,
        fingerprint: str,
        level: float,
        seed: int,
        perturbation: Perturbation,
        estimator: Any,
        context: RunContext,
        candidates: CandidateSink,
    ) -> None:
        self.fingerprint = fingerprint
        self.level = level
        self.seed = seed
        self.perturbation = perturbation
        self.estimator = estimator
        self.context = context
        self.candidates = candidates
        self.done: list[str] = []
        self.predictions: dict[str, Prediction] = {}  # sau tấn công, đã lọc class đích
        self.stats: dict[str, ImageAttackStats] = {}
        self.top: list[str] = []  # top-K hiện tại, theo thứ tự của `select_failure_cases`
        self.offered: list[str] = []  # mọi ảnh đã giao cho `candidates` (chưa discard)
        # Ground truth và ignore region (kèm nguồn) của ứng viên trong top-K, cho FailureCaseRecord.
        self.case_inputs: dict[str, dict[str, Any]] = {}
        self.processing_seconds = 0.0

    # ------------------------------------------------------------------ tiến độ

    @property
    def images_total(self) -> int:
        return len(self.context.image_ids)

    @property
    def images_done(self) -> int:
        return len(self.done)

    def remaining_ids(self) -> list[str]:
        done = set(self.done)
        return [i for i in self.context.image_ids if i not in done]

    def batches(self, loader: SliceLoader, batch_size: int) -> Iterator[Batch]:
        """Batch của các ảnh chưa xử lý, theo thứ tự của slice."""
        if batch_size < 1:
            raise ValueError("batch_size phải ≥ 1")
        ids = self.remaining_ids()
        for start in range(0, len(ids), batch_size):
            chunk = ids[start : start + batch_size]
            loaded = [loader.load(image_id) for image_id in chunk]
            yield Batch(
                image_ids=list(chunk),
                images=np.stack([item[0] for item in loaded]),
                targets=[item[1] for item in loaded],
                ignore=[item[2] for item in loaded],
                infos=[item[3] for item in loaded],
            )

    # ------------------------------------------------------------------ xử lý

    def process_batch(self, batch: Batch) -> float:
        """Attack, predict và thống kê một batch; trả thời gian xử lý (giây)."""
        remaining = set(self.remaining_ids())
        if len(set(batch.image_ids)) != len(batch.image_ids) or not remaining.issuperset(
            batch.image_ids
        ):
            raise ValueError("Batch có ảnh đã xử lý, ảnh trùng hoặc ảnh ngoài slice")
        ctx = self.context
        start = time.perf_counter()
        mask = letterbox_mask(batch.infos)
        # Phase 6 (plan task 15a): mỗi target có `image_id` (seed theo ảnh) và `ignore_boxes`
        # (occlusion không tô lên ignore region). Adapter ART chỉ đọc `boxes`, `labels`.
        targets = [
            {**target, "image_id": image_id, "ignore_boxes": ignore["boxes"]}
            for target, image_id, ignore in zip(
                batch.targets, batch.image_ids, batch.ignore, strict=True
            )
        ]
        adversarial = self.perturbation.apply(batch.images, targets, self.level, self.seed, mask)
        preds = self.estimator.predict(adversarial, batch_size=len(batch.image_ids))
        elapsed = time.perf_counter() - start

        for i, image_id in enumerate(batch.image_ids):
            attacked = filter_classes(preds[i], ctx.target_labels)
            stats = image_attack_stats(
                ctx.clean_predictions[image_id],
                attacked,
                batch.targets[i],
                batch.ignore[i]["boxes"],
                ctx.target_labels,
                ctx.params.operating_conf,
            )
            self.predictions[image_id] = attacked
            self.stats[image_id] = stats
            self._offer(image_id, stats, batch, i, adversarial[i], preds[i])
            self.done.append(image_id)
        self.processing_seconds += elapsed
        return elapsed

    def _offer(
        self,
        image_id: str,
        stats: ImageAttackStats,
        batch: Batch,
        index: int,
        adversarial: NDArray[np.float32],
        attacked_raw: Prediction,
    ) -> None:
        limit = self.context.failure_cases_per_run
        if limit == 0 or stats.severity_score <= 0:
            return
        pool = {k: self.stats[k] for k in self.top}
        pool[image_id] = stats
        new_top = [k for k, _ in select_failure_cases(pool, limit)]
        if image_id in new_top:
            ignore = batch.ignore[index]
            _, height, width = adversarial.shape
            # Phase 6 (plan task 23, ml-privacy): làm mờ trước khi lưu ảnh hiển thị.
            regions = case_regions(
                ground_truth=batch.targets[index],
                clean=self.context.clean_predictions[image_id],
                attacked=attacked_raw,
                ignore_boxes=ignore["boxes"],
                class_names=self.context.class_names,
                width=width,
                height=height,
            )
            self.candidates.add(image_id, batch.images[index], adversarial, regions)
            self.offered.append(image_id)
            self.case_inputs[image_id] = {
                "gt_boxes": np.asarray(batch.targets[index]["boxes"]).reshape(-1, 4).tolist(),
                "gt_labels": np.asarray(batch.targets[index]["labels"]).tolist(),
                "ignore_boxes": np.asarray(ignore["boxes"]).reshape(-1, 4).tolist(),
                "ignore_sources": list(ignore["sources"]),
                "blur_regions": len(regions),
            }
        for evicted in [k for k in self.top if k not in new_top]:
            self.candidates.evict(evicted)
            self.case_inputs.pop(evicted, None)
        self.top = new_top

    # ------------------------------------------------------------------ hoàn tất

    def finalize(self, run_id: UUID, *, partial: bool = False) -> FinalizedRun:
        """Metric và failure case. `partial = True` (dừng do giới hạn): metric, kể cả mAP sạch,
        tính trên đúng các ảnh đã xử lý và `metrics.partial = true`."""
        ctx = self.context
        if not partial and self.remaining_ids():
            raise ValueError(f"Còn {len(self.remaining_ids())} ảnh chưa xử lý")
        done = set(self.done)
        ids = [i for i in ctx.image_ids if i in done]
        if not ids:
            raise ValueError("Chưa xử lý ảnh nào: không có metric")
        metric = ctx.new_metric()
        metric.update(
            [self.predictions[i] for i in ids],
            [ctx.targets[i] for i in ids],
            [ctx.ignore_boxes[i] for i in ids],
        )
        clean = ctx.clean_metrics_on(ids) if partial else ctx.clean_metrics
        metrics = build_run_metrics(clean, metric.compute(), [self.stats[i] for i in ids])
        if partial:
            metrics = metrics.model_copy(update={"partial": True})

        selected = select_failure_cases({i: self.stats[i] for i in ids}, ctx.failure_cases_per_run)
        if [image_id for image_id, _ in selected] != self.top:
            raise RuntimeError("Failure case giữ trong lúc chạy lệch với select_failure_cases")
        cases = [self._record(run_id, image_id, stats) for image_id, stats in selected]
        chosen = {image_id for image_id, _ in selected}
        for image_id in self.offered:
            if image_id not in chosen:
                self.candidates.discard(image_id)
        return FinalizedRun(metrics=metrics, failure_cases=cases, images_done=len(ids))

    def _boxes(self, pred: Prediction, ignore: NDArray[Any]) -> list[CaseBox]:
        ctx = self.context
        kept = filter_ignored(filter_classes(pred, ctx.target_labels), ignore)
        confident = kept["scores"] >= ctx.params.operating_conf
        return [
            CaseBox(bbox=bbox(box), class_name=ctx.class_names[int(label)], score=float(score))
            for box, label, score in zip(
                kept["boxes"][confident],
                kept["labels"][confident],
                kept["scores"][confident],
                strict=True,
            )
        ]

    def _record(self, run_id: UUID, image_id: str, stats: ImageAttackStats) -> FailureCaseRecord:
        ctx = self.context
        inputs = self.case_inputs[image_id]
        ignore_boxes = np.asarray(inputs["ignore_boxes"], dtype=np.float32).reshape(-1, 4)
        case_id = compute_failure_case_id(self.fingerprint, run_id, image_id)
        detections = CaseDetections(
            ground_truth=[
                CaseBox(bbox=bbox(box), class_name=ctx.class_names[int(label)], score=None)
                for box, label in zip(
                    np.asarray(inputs["gt_boxes"], dtype=np.float32).reshape(-1, 4),
                    inputs["gt_labels"],
                    strict=True,
                )
            ],
            clean=self._boxes(ctx.clean_predictions[image_id], ignore_boxes),
            attacked=self._boxes(self.predictions[image_id], ignore_boxes),
            ignore_regions=[
                CaseIgnoreRegion(bbox=bbox(box), source=source)
                for box, source in zip(ignore_boxes, inputs["ignore_sources"], strict=True)
            ],
        )
        return FailureCaseRecord(
            id=case_id,
            run_id=run_id,
            fingerprint=self.fingerprint,
            image_id=image_id,
            lost_objects=stats.lost,
            new_false_positives=stats.new_false_positives,
            severity_score=stats.severity_score,
            detections=detections,
            artifacts=self.candidates.promote(image_id, case_id),
            # Checkpoint cũ (trước Phase 6) không có `blur_regions`: ảnh ứng viên chưa làm mờ.
            anonymization=(
                anonymization(inputs["blur_regions"]) if "blur_regions" in inputs else None
            ),
        )

    # ------------------------------------------------------------------ checkpoint

    def to_checkpoint(self) -> dict[str, Any]:
        """Trạng thái sau batch vừa xử lý (JSON, không chứa ảnh)."""
        return {
            "version": CHECKPOINT_VERSION,
            "fingerprint": self.fingerprint,
            "images_total": self.images_total,
            "done": list(self.done),
            "predictions": {i: _pred_to_json(self.predictions[i]) for i in self.done},
            "stats": {i: _stats_to_json(self.stats[i]) for i in self.done},
            "top": list(self.top),
            "offered": list(self.offered),
            "case_inputs": {i: self.case_inputs[i] for i in self.top},
            "processing_seconds": self.processing_seconds,
        }

    @classmethod
    def from_checkpoint(
        cls,
        checkpoint: dict[str, Any],
        *,
        fingerprint: str,
        level: float,
        seed: int,
        perturbation: Perturbation,
        estimator: Any,
        context: RunContext,
        candidates: CandidateSink,
    ) -> RunExecutor:
        if checkpoint.get("version") != CHECKPOINT_VERSION:
            raise CheckpointMismatchError(f"Checkpoint version {checkpoint.get('version')!r}")
        if checkpoint["fingerprint"] != fingerprint:
            raise CheckpointMismatchError("Checkpoint thuộc run có fingerprint khác")
        slice_ids = set(context.image_ids)
        if checkpoint["images_total"] != len(context.image_ids) or not slice_ids.issuperset(
            checkpoint["done"]
        ):
            raise CheckpointMismatchError("Checkpoint không khớp ảnh của slice")
        executor = cls(
            fingerprint=fingerprint,
            level=level,
            seed=seed,
            perturbation=perturbation,
            estimator=estimator,
            context=context,
            candidates=candidates,
        )
        executor.done = list(checkpoint["done"])
        executor.predictions = {i: _pred_from_json(p) for i, p in checkpoint["predictions"].items()}
        executor.stats = {i: ImageAttackStats(**s) for i, s in checkpoint["stats"].items()}
        executor.top = list(checkpoint["top"])
        executor.offered = list(checkpoint["offered"])
        executor.case_inputs = dict(checkpoint["case_inputs"])
        executor.processing_seconds = float(checkpoint["processing_seconds"])
        if set(executor.predictions) != set(executor.done) or set(executor.stats) != set(
            executor.done
        ):
            raise CheckpointMismatchError("Checkpoint thiếu prediction hoặc thống kê của ảnh")
        if set(executor.top) != set(executor.case_inputs):
            raise CheckpointMismatchError("Checkpoint thiếu dữ liệu của ứng viên")
        return executor
