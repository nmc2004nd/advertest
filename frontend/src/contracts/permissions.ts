// Sinh bởi scripts/gen_contracts.py từ advertest_contracts.permissions. Không sửa tay.
import type { Permission, Role } from "./schemas";

/** Giá trị `x-permission` của endpoint chỉ cần đăng nhập. */
export const AUTHENTICATED = "authenticated" as const;

export const ROLE_PERMISSIONS: Readonly<Record<Role, readonly Permission[]>> = {
  "engineer": ["attack_catalog.read", "compute_target.read", "dataset.read", "dataset.upload", "experiment.cancel_own", "experiment.create", "experiment.read", "experiment.submit_review", "model.read", "protocol.read", "report.read", "review.comment", "slice.create"],
  "reviewer": ["attack_catalog.read", "dataset.read", "experiment.read", "model.read", "protocol.manage", "protocol.read", "report.export", "report.read", "review.comment", "review.decide"],
  "admin": ["attack_catalog.manage", "attack_catalog.read", "audit.read", "budget.manage", "compute_target.manage", "compute_target.read", "dataset.read", "experiment.read", "model.manage", "model.read", "protocol.read", "report.read", "user.manage"],
};
