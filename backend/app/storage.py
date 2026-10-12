"""MinIO của backend: client S3 có thông tin đăng nhập (chỉ API và CLI quản trị dùng) và bố cục
khóa trong các bucket (requirements.md Phase 3, mục Bố cục lưu trữ trong MinIO).

Worker không dùng module này: nó chỉ có presigned URL do API cấp.

Bản triển khai trên Railway (deploy/railway/README.md) chỉ có một bucket S3 với tên do Railway đặt:
khi có `MINIO_BUCKET`, bốn bucket logic thành tiền tố khóa trong bucket đó (`models/<key>`...).
URI lưu trong DB (`s3://artifacts/...`) và khóa mà code thấy vẫn là khóa logic.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, cast

import boto3
from botocore.config import Config

from ml_core.store import MinioStore, S3Client

BUCKET_MODELS = "models"
BUCKET_DATASETS = "datasets"
BUCKET_ARTIFACTS = "artifacts"
BUCKET_REPORTS = "reports"  # Phase 8: snapshot, JSON, PDF của report chính thức


def single_bucket() -> str | None:
    """Bucket vật lý duy nhất (`MINIO_BUCKET`), hoặc None khi mỗi bucket logic là một bucket."""
    return os.environ.get("MINIO_BUCKET") or None


def s3_location(bucket: str, key: str) -> tuple[str, str]:
    """(bucket, khóa) vật lý của một khóa trong bucket logic."""
    physical = single_bucket()
    return (physical, f"{bucket}/{key}") if physical else (bucket, key)


def s3_config(**extra: Any) -> Config:
    """Region và kiểu địa chỉ: MinIO dùng path-style; Railway dùng virtual-hosted, region `auto`."""
    return Config(
        region_name=os.environ.get("MINIO_REGION") or "us-east-1",
        signature_version="s3v4",
        s3={"addressing_style": os.environ.get("MINIO_ADDRESSING_STYLE") or "path"},
        **extra,
    )


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
        config=s3_config(),
    )
    return cast(S3Client, client)


class _PrefixedPaginator:
    def __init__(self, paginator: Any, physical: str, prefix: str) -> None:
        self._paginator = paginator
        self._physical = physical
        self._prefix = prefix

    def paginate(self, *, Bucket: str, Prefix: str = "", **kwargs: Any) -> Any:
        for page in self._paginator.paginate(
            Bucket=self._physical, Prefix=self._prefix + Prefix, **kwargs
        ):
            contents = [
                {**item, "Key": item["Key"].removeprefix(self._prefix)}
                for item in page.get("Contents", [])
            ]
            yield {**page, "Contents": contents}


class PrefixedClient:
    """Client S3 cho một bucket logic nằm dưới tiền tố `<bucket>/` của bucket vật lý: đổi
    Bucket/Key khi gọi, bỏ tiền tố khỏi khóa trả về khi liệt kê."""

    def __init__(self, client: S3Client, physical: str, prefix: str) -> None:
        self._client = client
        self._physical = physical
        self._prefix = prefix

    def put_object(self, *, Bucket: str, Key: str, Body: bytes) -> Any:
        return self._client.put_object(Bucket=self._physical, Key=self._prefix + Key, Body=Body)

    def get_object(self, *, Bucket: str, Key: str) -> Any:
        return self._client.get_object(Bucket=self._physical, Key=self._prefix + Key)

    def head_object(self, *, Bucket: str, Key: str) -> Any:
        return self._client.head_object(Bucket=self._physical, Key=self._prefix + Key)

    def delete_object(self, *, Bucket: str, Key: str) -> Any:
        return self._client.delete_object(Bucket=self._physical, Key=self._prefix + Key)

    def get_paginator(self, operation_name: str) -> Any:
        if operation_name != "list_objects_v2":
            raise NotImplementedError(operation_name)
        return _PrefixedPaginator(
            self._client.get_paginator(operation_name), self._physical, self._prefix
        )


def _store(client: S3Client, bucket: str) -> MinioStore:
    physical = single_bucket()
    if physical:
        return MinioStore(PrefixedClient(client, physical, f"{bucket}/"), bucket)
    return MinioStore(client, bucket)


@dataclass(frozen=True)
class Buckets:
    models: MinioStore
    datasets: MinioStore
    artifacts: MinioStore
    reports: MinioStore

    @classmethod
    def from_client(cls, client: S3Client) -> Buckets:
        return cls(
            models=_store(client, BUCKET_MODELS),
            datasets=_store(client, BUCKET_DATASETS),
            artifacts=_store(client, BUCKET_ARTIFACTS),
            reports=_store(client, BUCKET_REPORTS),
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
