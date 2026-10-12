"""Chế độ một bucket (`MINIO_BUCKET`, bản triển khai Railway): bucket logic thành tiền tố khóa,
code vẫn thấy khóa logic; presigned URL trỏ vào bucket vật lý."""

from __future__ import annotations

import io
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

import pytest

from backend.app import storage
from backend.app.presign import Presigner

NOW = datetime(2026, 1, 1, tzinfo=UTC)


class FakeS3:
    """Client S3 trong bộ nhớ, ghi (bucket, khóa) vật lý."""

    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def put_object(self, *, Bucket: str, Key: str, Body: bytes) -> None:
        self.objects[(Bucket, Key)] = Body

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        if (Bucket, Key) not in self.objects:
            raise _not_found()
        return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        if (Bucket, Key) not in self.objects:
            raise _not_found()
        return {"ETag": ""}

    def delete_object(self, *, Bucket: str, Key: str) -> None:
        self.objects.pop((Bucket, Key), None)

    def get_paginator(self, operation_name: str) -> Any:
        fake = self

        class Paginator:
            def paginate(self, *, Bucket: str, Prefix: str = "") -> Any:
                keys = sorted(k for b, k in fake.objects if b == Bucket and k.startswith(Prefix))
                yield {"Contents": [{"Key": k} for k in keys]}

        return Paginator()


def _not_found() -> Exception:
    exc = Exception("not found")
    exc.response = {"Error": {"Code": "NoSuchKey"}}  # type: ignore[attr-defined]
    return exc


def test_without_single_bucket_logical_bucket_is_physical(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MINIO_BUCKET", raising=False)
    client = FakeS3()
    buckets = storage.Buckets.from_client(client)
    buckets.models.put("a/weights.pt", b"w")
    assert client.objects == {("models", "a/weights.pt"): b"w"}
    assert storage.s3_location("models", "a/weights.pt") == ("models", "a/weights.pt")


def test_single_bucket_prefixes_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINIO_BUCKET", "advertest-x1y2")
    client = FakeS3()
    buckets = storage.Buckets.from_client(client)
    buckets.models.put("a/weights.pt", b"w")
    buckets.artifacts.put("runs/r1/x.json", b"x")
    buckets.artifacts.put("quick-tries/q1/in.png", b"q")

    assert set(client.objects) == {
        ("advertest-x1y2", "models/a/weights.pt"),
        ("advertest-x1y2", "artifacts/runs/r1/x.json"),
        ("advertest-x1y2", "artifacts/quick-tries/q1/in.png"),
    }
    assert buckets.models.get("a/weights.pt") == b"w"
    assert buckets.models.exists("a/weights.pt")
    assert not buckets.artifacts.exists("a/weights.pt")
    assert buckets.artifacts.list("runs/") == ["runs/r1/x.json"]
    assert buckets.artifacts.list() == ["quick-tries/q1/in.png", "runs/r1/x.json"]
    assert buckets.models.list() == ["a/weights.pt"]
    buckets.artifacts.delete("runs/r1/x.json")
    assert buckets.artifacts.list("runs/") == []


def test_single_bucket_presigned_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINIO_BUCKET", "advertest-x1y2")
    monkeypatch.setenv("MINIO_REGION", "auto")
    monkeypatch.setenv("MINIO_ADDRESSING_STYLE", "virtual")
    signer = Presigner.for_endpoint("https://t3.storageapi.dev", "ak", "sk")
    url = urlsplit(signer.url("artifacts", "runs/r1/x.json", "PUT", NOW).url)
    assert url.netloc == "advertest-x1y2.t3.storageapi.dev"
    assert url.path == "/artifacts/runs/r1/x.json"
    assert "%2Fauto%2Fs3%2Faws4_request" in url.query


def test_default_presigned_url_is_path_style(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("MINIO_BUCKET", "MINIO_REGION", "MINIO_ADDRESSING_STYLE"):
        monkeypatch.delenv(name, raising=False)
    signer = Presigner.for_endpoint("http://127.0.0.1:9000", "ak", "sk")
    url = urlsplit(signer.url("artifacts", "runs/r1/x.json", "GET", NOW).url)
    assert url.netloc == "127.0.0.1:9000"
    assert url.path == "/artifacts/runs/r1/x.json"
    assert "%2Fus-east-1%2Fs3%2Faws4_request" in url.query
