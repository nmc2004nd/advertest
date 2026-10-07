"""Fingerprint của run (tech-stack.md mục 4.4, requirements.md Phase 2 mục Fingerprint).

Không gồm batch size, thiết bị hay compute target: kết quả được dùng lại giữa các máy.

`FingerprintService` (Phase R1) dùng chung cho CLI và worker: đọc provenance một lần, rồi dựng
`FingerprintInputs` cho từng run của cùng model, slice và mapping.
"""

from __future__ import annotations

from typing import Any

from advertest_contracts.hashing import compute_fingerprint, sha256_of
from advertest_contracts.models import (
    AttackSpec,
    ClassMapping,
    FingerprintInputs,
    InferenceParams,
    LibVersions,
    SliceSpec,
)
from ml_core.preprocess import LETTERBOX_CONFIG
from ml_core.runner.env import GitState
from ml_core.runner.provenance import Provenance


def run_config_sha256(
    spec: AttackSpec, level: float, params: InferenceParams, mapping: ClassMapping
) -> str:
    """Hash cấu hình riêng của một run."""
    return sha256_of(
        {
            "spec_sha256": spec.spec_sha256,
            "level": level,
            "fixed_params": spec.fixed_params,
            "inference_params": params.model_dump(mode="json"),
            "letterbox": dict(LETTERBOX_CONFIG),
            "class_mapping_sha256": mapping.mapping_sha256,
        }
    )


def build_fingerprint_inputs(
    *,
    spec: AttackSpec,
    level: float,
    seed: int,
    params: InferenceParams,
    mapping: ClassMapping,
    slice_spec: SliceSpec,
    weights_sha256: str,
    git_commit: str,
    git_dirty: bool,
    lib_versions: LibVersions,
    docker_image_digest: str,
    patch_key: str | None = None,
    eval_image_ids_sha256: str | None = None,
) -> FingerprintInputs:
    """`patch_key` (Phase 6, plan task 18): khóa patch của run patch; null với run khác (bỏ khỏi
    JSON nên fingerprint của run khác không đổi). `eval_image_ids_sha256` (Phase 7, plan task 13):
    chỉ với run trên tập con (`ml_core.search.subset.eval_image_ids_sha256`); null với run toàn
    slice để điểm toàn slice trúng cache của run quét lưới."""
    level_param: dict[str, Any] = {spec.primary_param.name: level}
    return FingerprintInputs(
        config_sha256=run_config_sha256(spec, level, params, mapping),
        weights_sha256=weights_sha256,
        dataset_version_sha256=slice_spec.dataset_version_sha256,
        slice_id=slice_spec.id,
        slice_sha256=slice_spec.slice_sha256,
        attack_spec_sha256=spec.spec_sha256,
        params=level_param,
        seed=seed,
        git_commit=git_commit,
        git_dirty=git_dirty,
        lib_versions=lib_versions,
        docker_image_digest=docker_image_digest,
        patch_key=patch_key,
        eval_image_ids_sha256=eval_image_ids_sha256,
    )


def fingerprint(inputs: FingerprintInputs) -> str:
    return compute_fingerprint(inputs)


class FingerprintService:
    """`FingerprintInputs` của các run trong một experiment (cùng model, slice, mapping và tham số
    suy luận). Provenance được đọc một lần, ở lần đầu cần tới."""

    def __init__(
        self,
        provenance: Provenance,
        *,
        params: InferenceParams,
        mapping: ClassMapping,
        slice_spec: SliceSpec,
        weights_sha256: str,
    ) -> None:
        self._provenance = provenance
        self.params = params
        self.mapping = mapping
        self.slice_spec = slice_spec
        self.weights_sha256 = weights_sha256
        self._read: tuple[GitState, LibVersions, str] | None = None

    def _pinned(self) -> tuple[GitState, LibVersions, str]:
        if self._read is None:
            p = self._provenance
            self._read = (p.git(), p.lib_versions(), p.docker_image_digest())
        return self._read

    @property
    def git(self) -> GitState:
        return self._pinned()[0]

    def inputs(
        self,
        spec: AttackSpec,
        level: float,
        seed: int,
        *,
        patch_key: str | None = None,
        eval_image_ids_sha256: str | None = None,
    ) -> FingerprintInputs:
        git, versions, digest = self._pinned()
        return build_fingerprint_inputs(
            spec=spec,
            level=level,
            seed=seed,
            params=self.params,
            mapping=self.mapping,
            slice_spec=self.slice_spec,
            weights_sha256=self.weights_sha256,
            git_commit=git.commit,
            git_dirty=git.dirty,
            lib_versions=versions,
            docker_image_digest=digest,
            patch_key=patch_key,
            eval_image_ids_sha256=eval_image_ids_sha256,
        )
