"""Cấu hình `advertest run` (`LocalRunConfig`, requirements.md Phase 2, mục Cấu hình chạy local).

Không thuộc contract: `ExperimentConfig` đầy đủ (protocol, compute target, giới hạn) dùng từ
Phase 3.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import yaml
from pydantic import BaseModel, ConfigDict, Field, PositiveInt, model_validator

from advertest_contracts.enums import RunMode
from advertest_contracts.hashing import sha256_of
from advertest_contracts.ids import content_id
from advertest_contracts.models import AttackConfig, AttackSpec
from attacks.registry import get_spec, load_catalog

DEFAULT_BATCH_SIZE = 8
DEFAULT_FAILURE_CASES = 20


class LocalRunConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    model_id: UUID
    slice_id: UUID
    mapping_id: UUID
    attacks: list[AttackConfig] = Field(min_length=1)
    device: str | None = Field(default=None, description="Ví dụ cpu, cuda:0; mặc định GPU nếu có")
    batch_size: PositiveInt = DEFAULT_BATCH_SIZE
    failure_cases_per_run: int = Field(default=DEFAULT_FAILURE_CASES, ge=0)

    @model_validator(mode="after")
    def _grid_only(self) -> LocalRunConfig:
        for attack in self.attacks:
            if attack.mode != RunMode.GRID:
                raise ValueError("Phase 2 chỉ hỗ trợ mode = grid")
        return self


def load_config(path: Path) -> LocalRunConfig:
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"{path}: cấu hình phải là một mapping YAML")
    return LocalRunConfig.model_validate(data)


def experiment_id(config: LocalRunConfig) -> UUID:
    """`content_id(sha256_of(cấu hình))` của run chạy bằng CLI."""
    return content_id(sha256_of(config.model_dump(mode="json")))


def resolve_specs(
    config: LocalRunConfig, catalog: list[AttackSpec] | None = None
) -> list[AttackSpec]:
    """Spec của từng attack theo `spec_sha256`; `attack_spec_id` phải khớp spec đó."""
    catalog = load_catalog() if catalog is None else catalog
    specs = []
    for attack in config.attacks:
        spec = get_spec(catalog, spec_sha256=attack.spec_sha256)
        if spec.id != attack.attack_spec_id:
            raise ValueError(
                f"attack_spec_id {attack.attack_spec_id} không khớp spec {spec.name} ({spec.id})"
            )
        specs.append(spec)
    return specs
