"""Presigned URL cho worker (requirements.md Phase 3, Decisions: worker không có thông tin đăng
nhập MinIO; presigned URL giới hạn trong thư mục của run, hết hạn sau 15 phút).

Ký bằng client trỏ vào endpoint MinIO mà worker nhìn thấy (`MINIO_PUBLIC_ENDPOINT`, mặc định
`MINIO_ENDPOINT`): chữ ký S3 gồm host, nên URL chỉ dùng được đúng qua host đó. Ký URL không
cần kết nối mạng.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

import boto3
from botocore.config import Config

Method = Literal["PUT", "GET", "DELETE"]
EXPIRES_S = 15 * 60
_CLIENT_METHOD = {"GET": "get_object", "PUT": "put_object", "DELETE": "delete_object"}


@dataclass(frozen=True)
class PresignedUrl:
    url: str
    expires_at: datetime


class Presigner:
    def __init__(self, client: Any, expires_s: int = EXPIRES_S) -> None:
        self.client = client
        self.expires_s = expires_s

    @classmethod
    def from_env(cls) -> Presigner:
        endpoint = os.environ.get("MINIO_PUBLIC_ENDPOINT") or os.environ.get("MINIO_ENDPOINT")
        if not endpoint:
            raise RuntimeError("Thiếu MINIO_PUBLIC_ENDPOINT hoặc MINIO_ENDPOINT")
        return cls.for_endpoint(
            endpoint, os.environ.get("MINIO_ACCESS_KEY"), os.environ.get("MINIO_SECRET_KEY")
        )

    @classmethod
    def for_endpoint(
        cls,
        endpoint: str,
        access_key: str | None,
        secret_key: str | None,
        expires_s: int = EXPIRES_S,
    ) -> Presigner:
        client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name="us-east-1",
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )
        return cls(client, expires_s)

    def url(self, bucket: str, key: str, method: Method, now: datetime) -> PresignedUrl:
        url: str = self.client.generate_presigned_url(
            ClientMethod=_CLIENT_METHOD[method],
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=self.expires_s,
        )
        return PresignedUrl(url=url, expires_at=now + timedelta(seconds=self.expires_s))
