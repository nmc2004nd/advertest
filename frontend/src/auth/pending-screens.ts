import { Ban, Clock, UserX, type LucideIcon } from 'lucide-react'

import { isAccountStatusCode, type AccountStatusCode } from './account-status'

export interface StatusScreen {
  title: string
  body: string
  icon: LucideIcon
}

/** Nội dung theo mã lỗi đăng nhập (requirements.md Phase 4, trang Chờ duyệt). */
export const PENDING_SCREENS: Record<AccountStatusCode, StatusScreen> = {
  account_pending: {
    title: 'Tài khoản đang chờ duyệt',
    body: 'Quản trị viên chưa duyệt yêu cầu truy cập của bạn. Hãy thử đăng nhập lại sau.',
    icon: Clock,
  },
  account_rejected: {
    title: 'Yêu cầu truy cập bị từ chối',
    body: 'Quản trị viên đã từ chối yêu cầu truy cập. Liên hệ quản trị viên nếu bạn cần biết lý do.',
    icon: UserX,
  },
  account_disabled: {
    title: 'Tài khoản đã bị vô hiệu hóa',
    body: 'Tài khoản này không dùng được nữa. Liên hệ quản trị viên nếu bạn cho rằng đây là nhầm lẫn.',
    icon: Ban,
  },
}

/** Mã không hợp lệ hoặc thiếu → coi như đang chờ duyệt (trang chỉ hiển thị, không cấp quyền gì). */
export function pendingScreen(code: string | null): StatusScreen {
  return PENDING_SCREENS[code && isAccountStatusCode(code) ? code : 'account_pending']
}
