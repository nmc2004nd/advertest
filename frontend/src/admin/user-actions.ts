import type { UserAdminView } from '@/contracts/schemas'

export type UserAction = 'approve' | 'reject' | 'roles' | 'disable' | 'enable' | 'reset-link'

/**
 * Hành động hiện theo trạng thái (requirements.md Phase 4, Luật quản trị): duyệt/từ chối chỉ với
 * `pending`; đổi role và tạo link chỉ với `active`/`disabled`; vô hiệu hóa với `active`, kích hoạt
 * với `disabled`. Backend vẫn kiểm tra lại (409).
 */
export function actionsFor(user: Pick<UserAdminView, 'status'>): UserAction[] {
  switch (user.status) {
    case 'pending':
      return ['approve', 'reject']
    case 'active':
      return ['roles', 'reset-link', 'disable']
    case 'disabled':
      return ['enable', 'roles', 'reset-link']
    case 'rejected':
      return []
  }
}

export const ACTION_LABELS: Record<UserAction, string> = {
  approve: 'Duyệt',
  reject: 'Từ chối',
  roles: 'Đổi role',
  disable: 'Vô hiệu hóa',
  enable: 'Kích hoạt',
  'reset-link': 'Tạo link đặt lại',
}
