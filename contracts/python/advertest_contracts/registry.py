"""Danh sách schema contract: tên thư mục mock / file JSON Schema → model Pydantic."""

from __future__ import annotations

from pydantic import BaseModel

from advertest_contracts.models import (
    AttackConfig,
    AttackSpec,
    DatasetManifest,
    ErrorResponse,
    ExperimentConfig,
    HealthResponse,
    Manifest,
    ProtocolBody,
    RunResult,
    SearchResult,
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
}
