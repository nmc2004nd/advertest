from pathlib import Path
from uuid import uuid4

import pytest

from advertest_contracts.ids import content_id
from ml_core.store import (
    KeyConflictError,
    KeyNotFoundError,
    LocalStore,
    register_id,
    resolve_id,
)

SHA = "a" * 64


@pytest.fixture
def store(tmp_path: Path) -> LocalStore:
    return LocalStore(tmp_path / "store")


def test_put_get_exists(store: LocalStore) -> None:
    key = f"datasets/{SHA}/manifest.json"
    assert not store.exists(key)
    store.put(key, b"{}")
    assert store.exists(key)
    assert store.get(key) == b"{}"
    assert (store.root / "datasets" / SHA / "manifest.json").read_bytes() == b"{}"


def test_put_same_content_is_noop(store: LocalStore) -> None:
    store.put("slices/x.json", b"1")
    store.put("slices/x.json", b"1")
    assert store.get("slices/x.json") == b"1"


def test_put_different_content_conflicts(store: LocalStore) -> None:
    store.put("slices/x.json", b"1")
    with pytest.raises(KeyConflictError):
        store.put("slices/x.json", b"2")
    assert store.get("slices/x.json") == b"1"


def test_get_missing(store: LocalStore) -> None:
    with pytest.raises(KeyNotFoundError):
        store.get("slices/missing.json")


def test_list_sorted_by_prefix_without_temp_files(store: LocalStore) -> None:
    for key in ("slices/b.json", "slices/a.json", "mappings/c.json"):
        store.put(key, b"x")
    (store.root / "slices" / ".tmp-abc").write_bytes(b"partial")
    assert store.list("slices/") == ["slices/a.json", "slices/b.json"]
    assert store.list() == ["mappings/c.json", "slices/a.json", "slices/b.json"]


def test_list_empty_store(tmp_path: Path) -> None:
    assert LocalStore(tmp_path / "chưa-có").list() == []


@pytest.mark.parametrize(
    "key",
    [
        "",
        "/abs/path",
        "../escape",
        "a/../b",
        "a//b",
        "a/./b",
        "a\\b",
        "a/b/",
        "có dấu",
        "a/.tmp-x",  # tên ẩn dành cho file tạm, list() không thấy
        ".hidden",
    ],
)
def test_invalid_keys_rejected(store: LocalStore, key: str) -> None:
    with pytest.raises(ValueError):
        store.put(key, b"x")
    with pytest.raises(ValueError):
        store.exists(key)


def test_id_index_roundtrip(store: LocalStore) -> None:
    id_ = register_id(store, "slice", SHA)
    assert id_ == content_id(SHA)
    assert register_id(store, "slice", SHA) == id_  # gọi lại an toàn
    assert resolve_id(store, "slice", id_) == SHA
    assert store.exists(f"index/slice/{id_}")


def test_id_index_is_per_kind(store: LocalStore) -> None:
    id_ = register_id(store, "model", SHA)
    with pytest.raises(KeyNotFoundError, match="slice"):
        resolve_id(store, "slice", id_)


def test_resolve_unknown_id(store: LocalStore) -> None:
    with pytest.raises(KeyNotFoundError):
        resolve_id(store, "dataset", uuid4())


def test_dots_inside_segment_allowed(store: LocalStore) -> None:
    store.put("models/abc/card.v1.json", b"x")
    assert store.list("models/") == ["models/abc/card.v1.json"]
