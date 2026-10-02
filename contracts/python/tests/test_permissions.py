import pytest

from advertest_contracts.enums import Role
from advertest_contracts.permissions import ROLE_PERMISSIONS, Permission, permissions_for

# Bảng "Ma trận quyền" trong specs/2026-09-27-phase-04-auth-rbac/requirements.md (E, R, A).
MATRIX = """
experiment.read           E R A
experiment.create         E
experiment.cancel_own     E
experiment.submit_review  E
dataset.read              E R A
dataset.upload            E
slice.create              E
model.read                E R A
model.manage                  A
attack_catalog.read       E R A
attack_catalog.manage         A
protocol.read             E R A
protocol.manage             R
review.decide               R
review.comment            E R
report.export               R
report.read               E R A
user.manage                   A
compute_target.read       E   A
compute_target.manage         A
budget.manage                 A
audit.read                    A
"""
LETTER = {"E": Role.ENGINEER, "R": Role.REVIEWER, "A": Role.ADMIN}
EXPECTED = {
    Permission(name): {LETTER[c] for c in cols}
    for name, *cols in (line.split() for line in MATRIX.strip().splitlines())
}


def test_permission_enum_matches_table() -> None:
    assert set(EXPECTED) == set(Permission)


@pytest.mark.parametrize("permission", list(Permission))
def test_every_cell_matches_table(permission: Permission) -> None:
    holders = {role for role, perms in ROLE_PERMISSIONS.items() if permission in perms}
    assert holders == EXPECTED[permission]


def test_every_role_has_an_entry() -> None:
    assert set(ROLE_PERMISSIONS) == set(Role)


def test_multiple_roles_get_the_union() -> None:
    assert permissions_for([Role.ENGINEER, Role.REVIEWER]) == (
        ROLE_PERMISSIONS[Role.ENGINEER] | ROLE_PERMISSIONS[Role.REVIEWER]
    )
    assert permissions_for([]) == frozenset()
