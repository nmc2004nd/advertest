"""Ma trận quyền dùng chung cho backend và frontend (requirements.md Phase 4).

Người dùng nhiều role có hợp các permission. Luật phụ thuộc đối tượng (chỉ hủy experiment của
mình, không review experiment của mình) kiểm tra ở tầng service, không nằm trong ma trận.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum
from typing import Final, Literal

from advertest_contracts.enums import Role


class Permission(StrEnum):
    EXPERIMENT_READ = "experiment.read"
    EXPERIMENT_CREATE = "experiment.create"
    EXPERIMENT_CANCEL_OWN = "experiment.cancel_own"
    EXPERIMENT_SUBMIT_REVIEW = "experiment.submit_review"
    DATASET_READ = "dataset.read"
    DATASET_UPLOAD = "dataset.upload"
    SLICE_CREATE = "slice.create"
    MODEL_READ = "model.read"
    MODEL_MANAGE = "model.manage"
    ATTACK_CATALOG_READ = "attack_catalog.read"
    ATTACK_CATALOG_MANAGE = "attack_catalog.manage"
    PROTOCOL_READ = "protocol.read"
    PROTOCOL_MANAGE = "protocol.manage"
    REVIEW_DECIDE = "review.decide"
    REVIEW_COMMENT = "review.comment"  # Phase 8: bình luận khi experiment đang được review
    REPORT_EXPORT = "report.export"
    REPORT_READ = "report.read"
    USER_MANAGE = "user.manage"
    COMPUTE_TARGET_READ = "compute_target.read"
    COMPUTE_TARGET_MANAGE = "compute_target.manage"
    BUDGET_MANAGE = "budget.manage"
    AUDIT_READ = "audit.read"


# Giá trị `x-permission` trong OpenAPI cho endpoint chỉ cần đăng nhập (mọi user `active`).
AUTHENTICATED: Final = "authenticated"
PermissionRequirement = Permission | Literal["authenticated"]

_P = Permission

ROLE_PERMISSIONS: Final[dict[Role, frozenset[Permission]]] = {
    Role.ENGINEER: frozenset(
        {
            _P.EXPERIMENT_READ,
            _P.EXPERIMENT_CREATE,
            _P.EXPERIMENT_CANCEL_OWN,
            _P.EXPERIMENT_SUBMIT_REVIEW,
            _P.REVIEW_COMMENT,
            _P.DATASET_READ,
            _P.DATASET_UPLOAD,
            _P.SLICE_CREATE,
            _P.MODEL_READ,
            _P.ATTACK_CATALOG_READ,
            _P.PROTOCOL_READ,
            _P.REPORT_READ,
            _P.COMPUTE_TARGET_READ,
        }
    ),
    Role.REVIEWER: frozenset(
        {
            _P.EXPERIMENT_READ,
            _P.DATASET_READ,
            _P.MODEL_READ,
            _P.ATTACK_CATALOG_READ,
            _P.PROTOCOL_READ,
            _P.PROTOCOL_MANAGE,
            _P.REVIEW_DECIDE,
            _P.REVIEW_COMMENT,
            _P.REPORT_EXPORT,
            _P.REPORT_READ,
        }
    ),
    Role.ADMIN: frozenset(
        {
            _P.EXPERIMENT_READ,
            _P.DATASET_READ,
            _P.MODEL_READ,
            _P.MODEL_MANAGE,
            _P.ATTACK_CATALOG_READ,
            _P.ATTACK_CATALOG_MANAGE,
            _P.PROTOCOL_READ,
            _P.REPORT_READ,
            _P.USER_MANAGE,
            _P.COMPUTE_TARGET_READ,
            _P.COMPUTE_TARGET_MANAGE,
            _P.BUDGET_MANAGE,
            _P.AUDIT_READ,
        }
    ),
}


def permissions_for(roles: Iterable[Role]) -> frozenset[Permission]:
    """Hợp các permission của mọi role người dùng có."""
    return frozenset().union(*(ROLE_PERMISSIONS[role] for role in roles))
