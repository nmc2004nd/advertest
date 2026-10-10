"""Nhận kết quả `spec_check`: chỉ từ job đang được lease (review Phase R2, phát hiện #6)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from advertest_contracts.enums import AttackSpecStatus, ToolJobKind
from advertest_contracts.models import SpecCheckResult
from backend.app.db import models as m
from backend.app.services.attack_catalog import apply_check
from backend.app.services.errors import Conflict

NOW = datetime(2026, 10, 10, tzinfo=UTC)


class _Session:
    def __init__(self, row: m.AttackSpecRow) -> None:
        self.row = row

    def get(self, entity: Any, ident: UUID, **_: Any) -> m.AttackSpecRow | None:
        return self.row if ident == self.row.id else None

    def flush(self) -> None:
        pass


def _setup(leased_by: UUID | None) -> tuple[Session, m.AttackSpecRow, m.ToolJob, SpecCheckResult]:
    row = m.AttackSpecRow(id=uuid4(), status=AttackSpecStatus.CHECKING, check=None)
    job = m.ToolJob(
        kind=ToolJobKind.SPEC_CHECK, payload={"spec_id": str(row.id)}, leased_by=leased_by
    )
    result = SpecCheckResult(
        spec_id=row.id,
        items=[],
        passed=False,
        error="quá giờ",
        checked_at=NOW,
        worker_target_id=UUID(int=0),
    )
    return cast(Session, _Session(row)), row, job, result


def test_job_not_leased_rejected_without_change() -> None:
    session, row, job, result = _setup(leased_by=None)
    with pytest.raises(Conflict):
        apply_check(session, job, result)
    assert row.status == AttackSpecStatus.CHECKING
    assert row.check is None


def test_worker_target_taken_from_lease() -> None:
    target = uuid4()
    session, row, job, result = _setup(leased_by=target)
    apply_check(session, job, result)
    assert row.status == AttackSpecStatus.CHECK_FAILED
    assert row.check is not None
    assert row.check["worker_target_id"] == str(target)
