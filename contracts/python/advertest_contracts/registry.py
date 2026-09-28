"""Danh sách schema contract: tên thư mục mock / file JSON Schema → model Pydantic."""

from __future__ import annotations

from pydantic import BaseModel

from advertest_contracts.models import (
    AttackConfig,
    AttackSpec,
    ClassMapping,
    CleanEvalResult,
    DatasetManifest,
    ErrorResponse,
    ExperimentConfig,
    HealthResponse,
    Manifest,
    ModelCard,
    ProtocolBody,
    RunResult,
    SearchResult,
    SliceSpec,
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
}
