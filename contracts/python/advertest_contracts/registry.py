"""Danh sách schema contract: tên thư mục mock / file JSON Schema → model Pydantic."""

from __future__ import annotations

from pydantic import BaseModel

from advertest_contracts.models import (
    ArtifactUrlRequest,
    ArtifactUrlResponse,
    AttackConfig,
    AttackSpec,
    ClassMapping,
    CleanEvalResult,
    CostProfile,
    DatasetManifest,
    ErrorResponse,
    ExperimentConfig,
    FailureCaseRecord,
    HealthResponse,
    HeartbeatRequest,
    Manifest,
    ModelCard,
    ProgressReport,
    ProtocolBody,
    RunCompletion,
    RunResult,
    RunStartRequest,
    RunStartResponse,
    SearchResult,
    SliceSpec,
    WorkerDirective,
    WorkerJobBundle,
    WorkerLease,
)

SCHEMAS: dict[str, type[BaseModel]] = {
    "attack_spec": AttackSpec,
    "attack_config": AttackConfig,
    "experiment_config": ExperimentConfig,
    "run_result": RunResult,
    "manifest": Manifest,
    "search_result": SearchResult,
    "protocol_body": ProtocolBody,
    "error_response": ErrorResponse,
    "health_response": HealthResponse,
    "dataset_manifest": DatasetManifest,
    "model_card": ModelCard,
    "class_mapping": ClassMapping,
    "slice_spec": SliceSpec,
    "clean_eval_result": CleanEvalResult,
    "failure_case_record": FailureCaseRecord,
    # Phase 3: API nội bộ của worker.
    "cost_profile": CostProfile,
    "worker_lease": WorkerLease,
    "worker_job_bundle": WorkerJobBundle,
    "heartbeat_request": HeartbeatRequest,
    "run_start_request": RunStartRequest,
    "run_start_response": RunStartResponse,
    "progress_report": ProgressReport,
    "worker_directive": WorkerDirective,
    "artifact_url_request": ArtifactUrlRequest,
    "artifact_url_response": ArtifactUrlResponse,
    "run_completion": RunCompletion,
}
