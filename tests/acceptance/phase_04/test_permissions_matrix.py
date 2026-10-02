"""validation.md Phase 4, Chung: `ROLE_PERMISSIONS` khớp từng ô với bảng trong requirements."""

from __future__ import annotations

import pytest

from advertest_contracts.enums import Role
from advertest_contracts.permissions import ROLE_PERMISSIONS, Permission

# Bảng "Ma trận quyền" của specs/2026-09-27-phase-04-auth-rbac/requirements.md (E, R, A); Phase 8
# thêm review.comment (requirements.md Phase 8, Ma trận quyền).
TABLE = """
experiment.read           E R A
experiment.create         E . .
experiment.cancel_own     E . .
experiment.submit_review  E . .
dataset.read              E R A
dataset.upload            E . .
slice.create              E . .
model.read                E R A
model.manage              . . A
attack_catalog.read       E R A
attack_catalog.manage     . . A
protocol.read             E R A
protocol.manage           . R .
review.decide             . R .
review.comment            E R .
report.export             . R .
report.read               E R A
user.manage               . . A
compute_target.read       E . A
compute_target.manage     . . A
budget.manage             . . A
audit.read                . . A
"""
COLUMNS = (Role.ENGINEER, Role.REVIEWER, Role.ADMIN)
CELLS = [
    (Permission(name), role, mark != ".")
    for name, *marks in (line.split() for line in TABLE.strip().splitlines())
    for role, mark in zip(COLUMNS, marks, strict=True)
]


def test_table_lists_every_permission_once() -> None:
    names = [line.split()[0] for line in TABLE.strip().splitlines()]
    assert sorted(names) == sorted(p.value for p in Permission)


@pytest.mark.parametrize(("permission", "role", "granted"), CELLS)
def test_cell(permission: Permission, role: Role, granted: bool) -> None:
    assert (permission in ROLE_PERMISSIONS[role]) is granted
