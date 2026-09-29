import type { UserAdminPage } from '@/contracts/schemas'

/** Số tài khoản chờ duyệt trên trang đầu (tối đa `limit`); còn trang sau thì thêm dấu "+". */
export const PENDING_COUNT_LIMIT = 100

export function pendingCountLabel(page: Pick<UserAdminPage, 'items' | 'next_cursor'>): string {
  return `${page.items.length}${page.next_cursor ? '+' : ''}`
}

/** Khóa cache của số tài khoản chờ duyệt (trang admin làm mới sau khi duyệt, từ chối). */
export const PENDING_USERS_QUERY_KEY = ['admin', 'users', 'pending-count'] as const
