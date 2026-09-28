"""Tạo `CleanEvalResult` (contract) từ metric và thông tin của lần đánh giá."""

from __future__ import annotations

from advertest_contracts.models import (
    CacheInfo,
    ClassMapping,
    CleanEvalResult,
    EvalMappingRef,
    EvalMetrics,
    EvalModelRef,
    EvalSliceRef,
    InferenceParams,
    LibVersions,
    ModelCard,
    SliceSpec,
    Timing,
)


def build_clean_eval_result(
    *,
    metrics: EvalMetrics,
    card: ModelCard,
    slice_spec: SliceSpec,
    mapping: ClassMapping,
    inference_params: InferenceParams,
    cache_key: str,
    cache_hit: bool,
    total_s: float,
    device: str,
    lib_versions: LibVersions,
    git_commit: str,
) -> CleanEvalResult:
    """`num_images` là số ảnh của slice; `sec_per_image = total_s / num_images`."""
    if mapping.model_id != card.id:
        raise ValueError("Mapping không thuộc model đã cho")
    if mapping.dataset_version_sha256 != slice_spec.dataset_version_sha256:
        raise ValueError("Mapping và slice thuộc hai dataset version khác nhau")
    num_images = len(slice_spec.image_ids)
    return CleanEvalResult(
        model=EvalModelRef(id=card.id, weights_sha256=card.weights_sha256),
        slice=EvalSliceRef(
            id=slice_spec.id,
            slice_sha256=slice_spec.slice_sha256,
            image_ids_sha256=slice_spec.image_ids_sha256,
            dataset_version_sha256=slice_spec.dataset_version_sha256,
        ),
        class_mapping=EvalMappingRef(id=mapping.id, mapping_sha256=mapping.mapping_sha256),
        inference_params=inference_params,
        metrics=metrics,
        num_images=num_images,
        cache=CacheInfo(key=cache_key, hit=cache_hit),
        timing=Timing(total_s=total_s, sec_per_image=total_s / num_images),
        device=device,
        lib_versions=lib_versions,
        git_commit=git_commit,
    )
