"""Đường dẫn artifact của run trong store (requirements.md Phase R1, `### Điều phối`).

Layout giữ nguyên như trước R1:
- CLI (`advertest run`, theo fingerprint): `runs/<fp>/` cho kết quả `completed` đầu tiên,
  `runs/<fp>/reruns/<run_id>/` khi chạy lại bằng `--force`, `runs/<fp>/attempts/<run_id>/` cho run
  `failed` hoặc `skipped`.
- Worker (theo run): `runs/<run_id>/`, URI gửi cho API có tiền tố `s3://artifacts/`.

Trong mỗi thư mục run: `manifest.json`, `result.json` (chỉ CLI), `cases/<id>/` (ảnh, và
`record.json` ở CLI), `candidates/<image_id>/` và `checkpoints/<batch>.json` (chỉ worker).
`predictions.json` của worker theo `ml_core.metrics.bootstrap.run_predictions_key`.
"""

from __future__ import annotations

from uuid import UUID

ARTIFACTS_URI = "s3://artifacts/"


def fingerprint_prefix(fp: str) -> str:
    return f"runs/{fp}"


def rerun_prefix(base: str, run_id: UUID) -> str:
    return f"{base}/reruns/{run_id}"


def attempt_prefix(base: str, run_id: UUID) -> str:
    return f"{base}/attempts/{run_id}"


def run_id_prefix(run_id: UUID) -> str:
    return f"runs/{run_id}"


def manifest_key(prefix: str) -> str:
    return f"{prefix}/manifest.json"


def result_key(prefix: str) -> str:
    return f"{prefix}/result.json"


def case_prefix(prefix: str, case_dir: object) -> str:
    """Thư mục của một failure case: theo `image_id` ở CLI, theo `case_id` ở worker."""
    return f"{prefix}/cases/{case_dir}"


def candidate_prefix(prefix: str, image_id: str) -> str:
    """Ảnh ứng viên failure case của worker, trước khi chốt top-K."""
    return f"{prefix}/candidates/{image_id}"


def case_record_key(prefix: str, image_id: str) -> str:
    return f"{case_prefix(prefix, image_id)}/record.json"


def checkpoint_key(prefix: str, batch_index: int) -> str:
    return f"{prefix}/checkpoints/{batch_index}.json"


def artifact_uri(key: str) -> str:
    return ARTIFACTS_URI + key
