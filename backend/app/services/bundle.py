"""Dựng `WorkerJobBundle` (requirements.md Phase 3, `GET /experiments/{id}/bundle`).

Card, slice, manifest đọc từ MinIO (bản `import-local` đã upload); mapping, attack spec, cost
profile đọc từ DB. Tài nguyên tải về (weights, manifest, ảnh của slice, checkpoint) là presigned
GET URL hết hạn sau 15 phút; worker gọi lại endpoint này để lấy URL mới.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from advertest_contracts.enums import EvalScope, ExperimentStatus, RunStatus
from advertest_contracts.models import (
    AttackSpec,
    BundleCheckpoint,
    BundleDownloads,
    BundleLimit,
    BundlePatch,
    BundleRun,
    ClassMapping,
    CostProfile,
    DatasetManifest,
    Environment,
    ExperimentConfig,
    InferenceParams,
    ModelCard,
    RunMetrics,
    SliceSpec,
    WorkerJobBundle,
)
from backend.app import storage
from backend.app.db import models as m
from backend.app.presign import Presigner
from backend.app.services import searches
from backend.app.services.clock import Clock, utcnow
from backend.app.services.errors import Conflict, Forbidden, NotFound
from backend.app.services.estimate import latest_profiles
from backend.app.services.experiments import runs_of
from backend.app.services.patches import registered, run_patch


def build(
    session: Session,
    target: m.ComputeTarget,
    experiment_id: UUID,
    buckets: storage.Buckets,
    presigner: Presigner,
    clock: Clock = utcnow,
) -> WorkerJobBundle:
    experiment = session.get(m.Experiment, experiment_id)
    if experiment is None:
        raise NotFound(f"Không có experiment {experiment_id}")
    if experiment.compute_target_id != target.id:
        raise Forbidden("Experiment thuộc compute target khác")
    if experiment.status != ExperimentStatus.RUNNING:
        raise Conflict(f"Experiment đang ở trạng thái {experiment.status}")
    now = clock()
    config = ExperimentConfig.model_validate(experiment.config)

    version = session.get(m.ModelVersion, experiment.model_version_id)
    slice_row = session.get(m.Slice, experiment.slice_id)
    mapping_row = session.get(m.ClassMapping, experiment.class_mapping_id)
    if version is None or slice_row is None or mapping_row is None:
        raise NotFound("Model, slice hoặc mapping của experiment không còn")
    if slice_row.slice_sha256 is None:
        raise Conflict(f"Slice {slice_row.id} chưa được đăng ký qua import-local")
    card = ModelCard.model_validate_json(
        buckets.models.get(storage.card_key(version.weights_sha256))
    )
    slice_spec = SliceSpec.model_validate_json(
        buckets.datasets.get(storage.slice_key(slice_row.slice_sha256))
    )
    dataset_sha = slice_spec.dataset_version_sha256
    manifest = DatasetManifest.model_validate_json(
        buckets.datasets.get(storage.manifest_key(dataset_sha))
    )
    image_sha = {img.image_id: img.sha256 for img in manifest.images}

    spec_ids = list(dict.fromkeys(a.attack_spec_id for a in config.attacks))
    spec_rows = {
        row.id: row
        for row in session.scalars(select(m.AttackSpecRow).where(m.AttackSpecRow.id.in_(spec_ids)))
    }
    attack_specs = [AttackSpec.model_validate(spec_rows[i].spec) for i in spec_ids]
    profiles = [
        CostProfile(
            compute_target_id=row.compute_target_id,
            model_version_id=row.model_version_id,
            attack_spec_id=row.attack_spec_id,
            sec_per_image=row.sec_per_image,
            peak_vram_mb=row.peak_vram_mb,
            batch_size=row.batch_size,
            measured_at=row.measured_at,
            environment=Environment.model_validate(row.environment),
            sec_per_image_iteration=row.sec_per_image_iteration,
        )
        for attack_id, row in latest_profiles(session, target.id, version.id).items()
        if attack_id in spec_rows and row.environment is not None
    ]

    def get_url(bucket: str, key: str) -> str:
        return presigner.url(bucket, key, "GET", now).url

    specs_by_id = {spec.id: spec for spec in attack_specs}
    training_slices: dict[UUID, SliceSpec] = {}
    patches: dict[str, BundlePatch] = {}
    runs = []
    for run in runs_of(session, experiment.id):
        # Phase 6: khóa patch của run patch, patch đã đăng ký hoặc checkpoint train dở.
        patch = run_patch(session, experiment, run, specs_by_id[run.attack_spec_id])
        if patch is not None:
            training = patch.training_slice
            if training.id not in training_slices:
                assert training.slice_sha256 is not None  # run_patch đã kiểm tra
                training_slices[training.id] = SliceSpec.model_validate_json(
                    buckets.datasets.get(storage.slice_key(training.slice_sha256))
                )
            if patch.key not in patches:
                artifact = registered(session, patch.key)
                row = session.get(m.Patch, patch.key)
                patches[patch.key] = BundlePatch(
                    key=patch.key,
                    attack_spec_id=run.attack_spec_id,
                    area_ratio=run.level,
                    training_slice_id=training.id,
                    artifact=artifact,
                    checkpoint_key=(
                        row.checkpoint_key if artifact is None and row is not None else None
                    ),
                )
        checkpoint = None
        if (
            run.status == RunStatus.RUNNING
            and run.checkpoint_key is not None
            and run.checkpoint_key.startswith(storage.run_prefix(run.id))
        ):
            checkpoint = BundleCheckpoint(
                batch_index=run.checkpoint_batch_index or 0,
                key=run.checkpoint_key,
                url=get_url(storage.BUCKET_ARTIFACTS, run.checkpoint_key),
            )
        runs.append(
            BundleRun(
                run_id=run.id,
                attack_spec_id=run.attack_spec_id,
                level=run.level,
                seed=run.seed,
                status=run.status,
                images_done=run.images_done,
                images_total=run.images_total,
                checkpoint=checkpoint,
                metrics=RunMetrics.model_validate(run.metrics) if run.metrics else None,
                patch_key=patch.key if patch is not None else None,
                scope=EvalScope(run.scope),
                search_order=run.search_order,
            )
        )
    image_ids = list(
        dict.fromkeys(
            [*slice_spec.image_ids, *(i for s in training_slices.values() for i in s.image_ids)]
        )
    )

    return WorkerJobBundle(
        experiment_id=experiment.id,
        config=config,
        model_card=card,
        slice=slice_spec,
        class_mapping=ClassMapping.model_validate(mapping_row.mapping),
        attack_specs=attack_specs,
        inference_params=InferenceParams.model_validate(experiment.inference_params),
        failure_cases_per_run=experiment.failure_cases_per_run or 0,
        cost_profiles=profiles,
        downloads=BundleDownloads(
            weights=get_url(storage.BUCKET_MODELS, storage.weights_key(version.weights_sha256)),
            dataset_manifest=get_url(storage.BUCKET_DATASETS, storage.manifest_key(dataset_sha)),
            images={
                image_id: get_url(
                    storage.BUCKET_DATASETS, storage.image_key(dataset_sha, image_sha[image_id])
                )
                for image_id in image_ids
            },
            expires_at=now + timedelta(seconds=presigner.expires_s),
        ),
        limit=BundleLimit(
            kind=experiment.limit_kind,
            value=experiment.limit_value,
            used=experiment.processing_seconds_used,
        ),
        runs=runs,
        training_slices=list(training_slices.values()),
        patches=list(patches.values()),
        search_results=searches.results(session, experiment.id),
    )
