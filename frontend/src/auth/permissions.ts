import { AUTHENTICATED, ROLE_PERMISSIONS } from '@/contracts/permissions'
import type { Me, Permission, Role } from '@/contracts/schemas'

/** Permission yêu cầu của một trang hoặc mục điều hướng: một Permission, hoặc chỉ cần đăng nhập. */
export type Requirement = Permission | typeof AUTHENTICATED

export { AUTHENTICATED }

/** Hợp các permission của mọi role (ma trận sinh từ contract, dùng chung với backend). */
export function permissionsFor(roles: readonly Role[]): ReadonlySet<Permission> {
  return new Set(roles.flatMap((role) => ROLE_PERMISSIONS[role]))
}

/**
 * Người dùng có quyền không. Tính từ `roles` theo ma trận của contract (không tin `permissions`
 * do server trả, dù hai giá trị phải trùng). Chỉ để ẩn giao diện cho gọn: backend mới là lớp chặn.
 */
export function can(me: Pick<Me, 'roles'> | null | undefined, requirement: Requirement): boolean {
  if (!me) return false
  if (requirement === AUTHENTICATED) return true
  return permissionsFor(me.roles).has(requirement)
}
