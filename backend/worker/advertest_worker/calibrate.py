"""Calibration cost profile (requirements.md Phase 3, Calibration và ước lượng).

Chạy trên n = min(20, số ảnh của slice) ảnh đầu; tăng batch size 1, 2, 4, ... tối đa min(n, 32);
dừng khi hết VRAM (giữ bậc trước) hoặc, trên CPU, khi `sec_per_image` không giảm so với bậc
trước (giữ bậc trước). Đo `sec_per_image` (attack + predict) và `peak_vram_mb` ở batch size được
chọn. Có một lượt khởi động trước khi đo để thời gian nạp lần đầu không làm lệch bậc 1.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

import numpy as np
import torch

from advertest_contracts.models import AttackSpec, CostProfile, Environment, WorkerJobBundle
from advertest_contracts.perturbation import Perturbation
from advertest_worker.pipeline import RunPipeline
from attacks.builders import DEFAULT_REGISTRY, BuildContext, PerturbationRegistry
from attacks.patch.calibration import measure_sec_per_image_iteration
from attacks.patch.geometry import Region, patch_side
from attacks.patch.training import training_params
from ml_core.data.loader import SliceLoader
from ml_core.runner.images import letterbox_mask

logger = logging.getLogger(__name__)
MAX_IMAGES = 20
MAX_BATCH = 32


@dataclass(frozen=True)
class Measurement:
    batch_size: int
    sec_per_image: float
    peak_vram_mb: int


def batch_sizes(n_images: int) -> list[int]:
    """1, 2, 4, ... không vượt quá min(n, 32)."""
    cap = min(n_images, MAX_BATCH)
    sizes, size = [], 1
    while size <= cap:
        sizes.append(size)
        size *= 2
    return sizes


def _is_cuda(device: str) -> bool:
    return device.startswith("cuda")


def measure(
    loader: SliceLoader,
    image_ids: list[str],
    estimator: Any,
    perturbation: Perturbation,
    level: float,
    seed: int,
    device: str,
) -> Measurement:
    """Attack + predict một batch gồm `image_ids`."""
    loaded = [loader.load(image_id) for image_id in image_ids]
    images = np.stack([item[0] for item in loaded])
    # Như `RunExecutor.process_batch` (Phase 6, plan task 15a): `image_id` cho seed theo ảnh của
    # corruption và occlusion, `ignore_boxes` cho occlusion.
    targets = [
        {**target, "image_id": image_id, "ignore_boxes": ignore["boxes"]}
        for image_id, (_, target, ignore, _) in zip(image_ids, loaded, strict=True)
    ]
    mask = letterbox_mask([item[3] for item in loaded])
    if _is_cuda(device):
        torch.cuda.reset_peak_memory_stats(device)
    start = time.perf_counter()
    adversarial = perturbation.apply(images, targets, level, seed, mask)
    estimator.predict(adversarial, batch_size=len(image_ids))
    elapsed = time.perf_counter() - start
    peak = int(torch.cuda.max_memory_allocated(device) / 2**20) if _is_cuda(device) else 0
    return Measurement(len(image_ids), elapsed / len(image_ids), peak)


def calibrate(
    *,
    loader: SliceLoader,
    estimator: Any,
    perturbation: Perturbation,
    level: float,
    seed: int,
    device: str,
    compute_target_id: UUID,
    model_version_id: UUID,
    attack_spec_id: UUID,
    environment: Environment,
    now: datetime,
) -> CostProfile:
    ids = loader.slice.image_ids[:MAX_IMAGES]
    measure(loader, ids[:1], estimator, perturbation, level, seed, device)  # khởi động
    best: Measurement | None = None
    for size in batch_sizes(len(ids)):
        try:
            current = measure(loader, ids[:size], estimator, perturbation, level, seed, device)
        except torch.cuda.OutOfMemoryError:
            logger.warning("Hết VRAM ở batch size %d; giữ batch size trước", size)
            if best is None:
                raise
            break
        finally:
            if _is_cuda(device):
                torch.cuda.empty_cache()
        logger.info("Calibration batch %d: %.3f s/ảnh", size, current.sec_per_image)
        if (
            best is not None
            and not _is_cuda(device)
            and current.sec_per_image >= best.sec_per_image
        ):
            break
        best = current
    assert best is not None  # batch_sizes luôn có ít nhất bậc 1
    return CostProfile(
        compute_target_id=compute_target_id,
        model_version_id=model_version_id,
        attack_spec_id=attack_spec_id,
        sec_per_image=max(best.sec_per_image, 1e-6),
        peak_vram_mb=best.peak_vram_mb,
        batch_size=best.batch_size,
        measured_at=now,
        environment=environment,
    )


# ---------------------------------------------------------------- patch (Phase 6)


def calibration_patch(
    spec: AttackSpec,
    loader: SliceLoader,
    estimator: Any,
    registry: PerturbationRegistry = DEFAULT_REGISTRY,
) -> Perturbation:
    """Patch ngẫu nhiên ở `area_ratio` lớn nhất, đặt vừa ảnh đầu của slice: đo `sec_per_image` của
    giai đoạn đánh giá (dán patch rồi predict) mà không cần patch đã train. Dựng qua registry
    (`BuildContext.patch`)."""
    _, _, _, info = loader.load(loader.slice.image_ids[0])
    mask = letterbox_mask([info])[0, 0]
    rows = np.flatnonzero(mask.any(axis=1))
    cols = np.flatnonzero(mask.any(axis=0))
    region = Region(int(rows[0]), int(rows[-1]) + 1, int(cols[0]), int(cols[-1]) + 1)
    side = patch_side(spec.primary_param.max, region)
    patch = np.random.default_rng(0).random((3, side, side)).astype(np.float32)
    area_ratio = spec.primary_param.max
    return registry.build(
        spec, BuildContext(estimator=estimator, patch=patch, area_ratio=area_ratio)
    )


def patch_training_cost(spec: AttackSpec, loader: SliceLoader, estimator: Any) -> float:
    """`sec_per_image_iteration`: 5 vòng train trên tối đa `training.batch_size` ảnh đầu."""
    n = min(len(loader.slice.image_ids), training_params(spec).batch_size)
    loaded = [loader.load(image_id) for image_id in loader.slice.image_ids[:n]]
    images = np.stack([item[0] for item in loaded])
    mask = letterbox_mask([item[3] for item in loaded])
    return measure_sec_per_image_iteration(spec, estimator, images, mask)


def calibrate_bundle(
    pipeline: RunPipeline, bundle: WorkerJobBundle, loader: SliceLoader, *, force: bool = False
) -> dict[UUID, CostProfile]:
    """Cost profile cho mọi attack của bundle; đo (và gửi lên API) attack chưa có profile,
    hoặc mọi attack khi `force`. Attack không dùng được với model thì bỏ qua."""
    profiles = {p.attack_spec_id: p for p in bundle.cost_profiles}
    card = bundle.model_card
    adapter = pipeline.adapter(bundle)
    for attack in bundle.config.attacks:
        spec = next(s for s in bundle.attack_specs if s.id == attack.attack_spec_id)
        if (spec.id in profiles and not force) or (
            spec.requires_gradients and not adapter.capabilities.gradients
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
                perturbation: Perturbation = calibration_patch(
                    spec, loader, adapter.estimator(), pipeline.registry
                )
                level = spec.primary_param.max
            else:
                perturbation = pipeline.build_perturbation(spec, bundle)
        except Exception:
            logger.warning("Không dựng được %s để calibration", spec.name, exc_info=True)
            continue
        profile = calibrate(
            loader=loader,
            estimator=adapter,
            perturbation=perturbation,
            level=level,
            seed=attack.seed,
            device=pipeline.device,
            compute_target_id=bundle.config.compute_target_id,
            model_version_id=card.id,
            attack_spec_id=spec.id,
            environment=pipeline.environment(bundle),
            now=pipeline.clock(),
        )
        if spec.requires_training:
            try:
                seconds = patch_training_cost(spec, loader, adapter.estimator())
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
        pipeline.client.cost_profile(profile)
        profiles[spec.id] = profile
    return profiles
