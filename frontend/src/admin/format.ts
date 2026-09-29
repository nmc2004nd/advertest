import type { AuditLogEntry, UserStatus } from '@/contracts/schemas'

/** Rút gọn chuỗi dài ở giữa: `abcd1234…ef90` (ID, hash). */
export function middleTruncate(value: string, head = 8, tail = 4): string {
  if (value.length <= head + tail + 1) return value
  return `${value.slice(0, head)}…${value.slice(-tail)}`
}

const DATE_TIME = new Intl.DateTimeFormat('vi-VN', {
  dateStyle: 'short',
  timeStyle: 'short',
})

export function formatDateTime(iso: string): string {
  return DATE_TIME.format(new Date(iso))
}

export const USER_STATUS_LABELS: Record<UserStatus, string> = {
  pending: 'Chờ duyệt',
  active: 'Đang hoạt động',
  rejected: 'Bị từ chối',
  disabled: 'Bị vô hiệu hóa',
}

export const AUDIT_ACTION_LABELS: Record<string, string> = {
  'user.access_requested': 'Yêu cầu truy cập',
  'user.approved': 'Duyệt tài khoản',
  'user.rejected': 'Từ chối tài khoản',
  'user.roles_changed': 'Đổi role',
  'user.disabled': 'Vô hiệu hóa',
  'user.enabled': 'Kích hoạt',
  'user.reset_link_created': 'Tạo link đặt lại mật khẩu',
  'user.password_changed': 'Đổi mật khẩu',
  'user.password_reset': 'Đặt lại mật khẩu',
}

export function actionLabel(action: string): string {
  return AUDIT_ACTION_LABELS[action] ?? action
}

function show(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(show).join(', ')}]`
  if (value === null || value === undefined) return '—'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

/** Mô tả gọn các trường thay đổi giữa `before` và `after` (`status: pending → active`). */
export function describeChange(entry: Pick<AuditLogEntry, 'before' | 'after'>): string[] {
  const before = entry.before ?? {}
  const after = entry.after ?? {}
  const keys = [...new Set([...Object.keys(before), ...Object.keys(after)])].sort()
  return keys
    .filter((key) => show(before[key]) !== show(after[key]) || !(key in before))
    .map((key) =>
      key in before
        ? `${key}: ${show(before[key])} → ${show(after[key])}`
        : `${key}: ${show(after[key])}`,
    )
}

/**
 * Khoảng ngày (theo giờ máy người dùng, dạng `YYYY-MM-DD` của `<input type="date">`) → tham số
 * UTC của API: `since` là đầu ngày bắt đầu (gồm), `until` là đầu ngày sau ngày kết thúc (không gồm).
 */
export function dayRangeToUtc(from: string, to: string): { since?: string; until?: string } {
  const range: { since?: string; until?: string } = {}
  if (from) range.since = new Date(`${from}T00:00:00`).toISOString()
  if (to) {
    const end = new Date(`${to}T00:00:00`)
    end.setDate(end.getDate() + 1)
    range.until = end.toISOString()
  }
  return range
}
