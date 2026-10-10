"""Kiểm header safetensors khi đăng ký model qua web (mission.md nguyên tắc 10)."""

from __future__ import annotations

import io
import json
import pickle
import struct
import zipfile
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

import numpy as np
import pytest
from safetensors.numpy import save
from sqlalchemy.orm import Session

from advertest_contracts.enums import ModelStatus, ToolJobKind
from advertest_contracts.models import ModelCheckResult
from backend.app import storage
from backend.app.db import models as m
from backend.app.services.errors import Conflict
from backend.app.services.model_uploads import apply_check, is_safetensors


def _raw(header: object, body: bytes = b"") -> bytes:
    encoded = json.dumps(header).encode()
    return struct.pack("<Q", len(encoded)) + encoded + body


def test_real_safetensors_accepted() -> None:
    data = save({"w": np.zeros((2, 3), dtype=np.float32), "b": np.ones(3, dtype=np.float32)})
    assert is_safetensors(data)


def _zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("archive/data.pkl", pickle.dumps({"w": [1, 2]}))
    return buffer.getvalue()


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"short",
        pickle.dumps({"weights": [1, 2, 3]}),
        _zip(),
        b"khong phai safetensors",
        struct.pack("<Q", 10**12) + b"{}",  # độ dài header vượt file
        _raw([1, 2]),  # không phải object
        _raw({}),  # không có tensor nào
        _raw({"__metadata__": {"a": "b"}}),
        _raw({"w": {"dtype": "F32", "shape": [2], "data_offsets": [0, 8]}}, b"1234"),  # vượt body
        _raw({"w": {"dtype": "F32", "shape": [-1], "data_offsets": [0, 0]}}),
        _raw({"w": {"shape": [1], "data_offsets": [0, 4]}}, b"1234"),  # thiếu dtype
        struct.pack("<Q", 4) + b"\xff\xfe{}",  # không phải UTF-8
    ],
)
def test_other_content_rejected(data: bytes) -> None:
    assert not is_safetensors(data)


def test_metadata_alongside_tensor_accepted() -> None:
    header = {
        "__metadata__": {"format": "pt"},
        "w": {"dtype": "F32", "shape": [1], "data_offsets": [0, 4]},
    }
    assert is_safetensors(_raw(header, b"\x00\x00\x80\x3f"))


# ---------------------------------------------------------------- nhận kết quả model_check


class _Session:
    def __init__(self, version: m.ModelVersion) -> None:
        self.version = version

    def get(self, entity: Any, ident: UUID, **_: Any) -> m.ModelVersion | None:
        return self.version if ident == self.version.id else None

    def flush(self) -> None:
        pass


def _check_setup(
    leased_by: UUID | None,
) -> tuple[Session, m.ModelVersion, m.ToolJob, ModelCheckResult]:
    version = m.ModelVersion(id=uuid4(), status=ModelStatus.CHECKING, check=None)
    job = m.ToolJob(
        kind=ToolJobKind.MODEL_CHECK,
        payload={"model_version_id": str(version.id)},
        leased_by=leased_by,
    )
    result = ModelCheckResult(
        passed=False,
        details="sha256 lệch",
        gradient_check=None,
        checked_at=datetime(2026, 10, 10, tzinfo=UTC),
        worker_target_id=UUID(int=0),
    )
    return cast(Session, _Session(version)), version, job, result


def test_check_from_unleased_job_rejected_without_change() -> None:
    """Review Phase R2, phát hiện #6: kiểm tường minh thay cho `assert`."""
    session, version, job, result = _check_setup(leased_by=None)
    with pytest.raises(Conflict):
        apply_check(session, job, result, cast(storage.Buckets, None))
    assert version.status == ModelStatus.CHECKING
    assert version.check is None


def test_check_worker_target_taken_from_lease() -> None:
    target = uuid4()
    session, version, job, result = _check_setup(leased_by=target)
    apply_check(session, job, result, cast(storage.Buckets, None))
    assert version.status == ModelStatus.CHECK_FAILED
    assert version.check is not None
    assert version.check["worker_target_id"] == str(target)
