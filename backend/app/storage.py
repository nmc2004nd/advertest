"""MinIO của backend: client S3 có thông tin đăng nhập (chỉ API và CLI quản trị dùng) và bố cục
khóa trong các bucket (requirements.md Phase 3, mục Bố cục lưu trữ trong MinIO).

Worker không dùng module này: nó chỉ có presigned URL do API cấp.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import cast

import boto3

from ml_core.store import MinioStore, S3Client

BUCKET_MODELS = "models"
BUCKET_DATASETS = "datasets"
BUCKET_ARTIFACTS = "artifacts"
BUCKET_REPORTS = "reports"  # Phase 8: snapshot, JSON, PDF của report chính thức


def make_s3_client(
    endpoint: str | None = None, access_key: str | None = None, secret_key: str | None = None
) -> S3Client:
    """Client S3 tới MinIO; mặc định đọc MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY."""
    endpoint = endpoint or os.environ.get("MINIO_ENDPOINT")
    if not endpoint:
        raise RuntimeError("Thiếu biến môi trường MINIO_ENDPOINT")
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key or os.environ.get("MINIO_ACCESS_KEY"),
        aws_secret_access_key=secret_key or os.environ.get("MINIO_SECRET_KEY"),
    )
    return cast(S3Client, client)


@dataclass(frozen=True)
class Buckets:
    models: MinioStore
    datasets: MinioStore
    artifacts: MinioStore
    reports: MinioStore

    @classmethod
    def from_client(cls, client: S3Client) -> Buckets:
        return cls(
            models=MinioStore(client, BUCKET_MODELS),
            datasets=MinioStore(client, BUCKET_DATASETS),
            artifacts=MinioStore(client, BUCKET_ARTIFACTS),
            reports=MinioStore(client, BUCKET_REPORTS),
        )


# ---------------------------------------------------------------- khóa


def weights_key(weights_sha256: str) -> str:
    return f"{weights_sha256}/weights.pt"


def card_key(weights_sha256: str) -> str:
    return f"{weights_sha256}/card.json"


def manifest_key(dataset_sha256: str) -> str:
    return f"{dataset_sha256}/manifest.json"


def image_key(dataset_sha256: str, image_sha256: str) -> str:
    return f"{dataset_sha256}/images/{image_sha256}.png"


def slice_key(slice_sha256: str) -> str:
    return f"slices/{slice_sha256}.json"


def mapping_key(mapping_sha256: str) -> str:
    return f"mappings/{mapping_sha256}.json"


def run_prefix(run_id: object) -> str:
    return f"runs/{run_id}/"
