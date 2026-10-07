"""`manifest.json` của run (tech-stack.md mục 4.4), dùng chung cho CLI và worker (Phase R1)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from advertest_contracts.models import Environment, FingerprintInputs, Manifest
from ml_core.runner.fingerprint import fingerprint
from ml_core.runner.paths import manifest_key


class ArtifactWriter(Protocol):
    """Phần ghi của store: `LocalStore`, `S3Store` hay `PresignedStore` của worker."""

    def put(self, key: str, data: bytes) -> None: ...


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ManifestBuilder:
    """Ghi `manifest.json` vào thư mục của run. `environment` được gọi mỗi lần ghi."""

    def __init__(
        self,
        environment: Callable[[], Environment],
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self.environment = environment
        self.clock = clock

    def build(self, run_id: UUID, inputs: FingerprintInputs) -> Manifest:
        return Manifest(
            run_id=run_id,
            fingerprint=fingerprint(inputs),
            fingerprint_inputs=inputs,
            environment=self.environment(),
            created_at=self.clock(),
        )

    def write(
        self, store: ArtifactWriter, prefix: str, run_id: UUID, inputs: FingerprintInputs
    ) -> str:
        """Ghi manifest, trả khóa trong store."""
        key = manifest_key(prefix)
        manifest = self.build(run_id, inputs)
        store.put(key, (manifest.model_dump_json(indent=2) + "\n").encode())
        return key
