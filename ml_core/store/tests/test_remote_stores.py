"""`MinioStore` (client S3 giả) và `PresignedStore` (`httpx.MockTransport`)."""

from __future__ import annotations

import hashlib
import io
from typing import Any

import httpx
import pytest

from ml_core.store import (
    ArtifactStore,
    DeletableStore,
    KeyConflictError,
    KeyNotFoundError,
    MinioStore,
    PresignedStore,
)


class ClientError(Exception):
    """Giống `botocore.exceptions.ClientError`: lỗi mang `response["Error"]["Code"]`."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class FakeS3:
    def __init__(self) -> None:
        self.buckets: dict[str, dict[str, bytes]] = {}
        self.puts = 0

    def _bucket(self, name: str) -> dict[str, bytes]:
        return self.buckets.setdefault(name, {})

    def put_object(self, *, Bucket: str, Key: str, Body: bytes) -> dict[str, Any]:
        self.puts += 1
        self._bucket(Bucket)[Key] = Body
        return {}

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        if Key not in self._bucket(Bucket):
            raise ClientError("NoSuchKey")
        return {"Body": io.BytesIO(self._bucket(Bucket)[Key])}

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        if Key not in self._bucket(Bucket):
            raise ClientError("404")
        return {"ETag": f'"{hashlib.md5(self._bucket(Bucket)[Key]).hexdigest()}"'}

    def delete_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        self._bucket(Bucket).pop(Key, None)
        return {}

    def get_paginator(self, operation_name: str) -> Any:
        assert operation_name == "list_objects_v2"
        fake = self

        class Paginator:
            def paginate(self, *, Bucket: str, Prefix: str) -> list[dict[str, Any]]:
                keys = sorted(k for k in fake._bucket(Bucket) if k.startswith(Prefix))
                # Hai trang để kiểm tra việc gộp trang.
                half = len(keys) // 2
                return [
                    {"Contents": [{"Key": k} for k in keys[:half]]},
                    {"Contents": [{"Key": k} for k in keys[half:]]} if keys[half:] else {},
                ]

        return Paginator()


def test_minio_store_roundtrip_and_immutability() -> None:
    s3 = FakeS3()
    store = MinioStore(s3, "artifacts")
    assert isinstance(store, ArtifactStore) and isinstance(store, DeletableStore)
    assert not store.exists("runs/r/a.json")
    store.put("runs/r/a.json", b"one")
    store.put("runs/r/a.json", b"one")  # cùng nội dung: no-op
    assert s3.puts == 1
    assert store.get("runs/r/a.json") == b"one" and store.exists("runs/r/a.json")
    with pytest.raises(KeyConflictError):
        store.put("runs/r/a.json", b"two")
    assert s3.buckets["artifacts"]["runs/r/a.json"] == b"one"


def test_minio_store_missing_list_delete_and_bad_key() -> None:
    store = MinioStore(FakeS3(), "datasets")
    with pytest.raises(KeyNotFoundError):
        store.get("x/missing.json")
    for key in ["a/1", "a/2", "b/1"]:
        store.put(key, key.encode())
    assert store.list("a/") == ["a/1", "a/2"]
    assert store.list() == ["a/1", "a/2", "b/1"]
    store.delete("a/1")
    store.delete("a/1")  # không tồn tại: no-op
    assert store.list("a/") == ["a/2"]
    for bad in ["../x", "/abs", "a//b", "a/.tmp"]:
        with pytest.raises(ValueError):
            store.put(bad, b"")


def test_minio_store_propagates_other_errors() -> None:
    class Broken(FakeS3):
        def head_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
            raise ClientError("AccessDenied")

    with pytest.raises(ClientError):
        MinioStore(Broken(), "artifacts").exists("a")


def _presigned(objects: dict[str, bytes]) -> tuple[PresignedStore, list[tuple[str, str]]]:
    requested: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        key = request.url.path.removeprefix("/artifacts/")
        assert request.url.params["sig"] == "ok"
        if request.method == "PUT":
            objects[key] = request.content
            return httpx.Response(200)
        if request.method == "DELETE":
            objects.pop(key, None)
            return httpx.Response(204)
        if key not in objects:
            return httpx.Response(404, text="<Error><Code>NoSuchKey</Code></Error>")
        return httpx.Response(200, content=objects[key])

    def url_for(key: str, method: str) -> str:
        requested.append((key, method))
        return f"http://minio:9000/artifacts/{key}?sig=ok"

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return PresignedStore(url_for, client), requested


def test_presigned_store_roundtrip() -> None:
    objects: dict[str, bytes] = {}
    store, requested = _presigned(objects)
    assert isinstance(store, DeletableStore)
    store.put("runs/r/checkpoints/0.json", b"{}")
    assert objects == {"runs/r/checkpoints/0.json": b"{}"}
    assert store.get("runs/r/checkpoints/0.json") == b"{}"
    assert store.exists("runs/r/checkpoints/0.json")
    store.delete("runs/r/checkpoints/0.json")
    assert not store.exists("runs/r/checkpoints/0.json")
    with pytest.raises(KeyNotFoundError):
        store.get("runs/r/checkpoints/0.json")
    store.delete("runs/r/checkpoints/0.json")  # không tồn tại: không lỗi
    assert {method for _, method in requested} == {"PUT", "GET", "DELETE"}


def test_presigned_store_rejects_bad_key_before_asking_url() -> None:
    store, requested = _presigned({})
    with pytest.raises(ValueError):
        store.put("runs/r/../other/x", b"")
    assert requested == []


def test_presigned_store_raises_on_server_error() -> None:
    client = httpx.Client(transport=httpx.MockTransport(lambda _r: httpx.Response(403)))
    store = PresignedStore(lambda key, method: f"http://minio/{key}", client)
    with pytest.raises(httpx.HTTPStatusError):
        store.put("runs/r/a", b"x")
    with pytest.raises(httpx.HTTPStatusError):
        store.get("runs/r/a")
    with pytest.raises(httpx.HTTPStatusError):
        store.delete("runs/r/a")
