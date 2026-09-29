import { ApiError } from './errors'

/**
 * Xử lý lỗi xác thực toàn cục (requirements.md Phase 4, Hành vi chung): `401 unauthenticated` →
 * `/login?next=<trang hiện tại>`, `403 forbidden` → `/forbidden`. Các mã khác
 * (`invalid_credentials`, `account_*`, `csrf_failed`, ...) để trang tự hiển thị.
 */
export function authRedirect(error: unknown, currentPath: string): string | null {
  if (!(error instanceof ApiError)) return null
  if (error.status === 401 && error.code === 'unauthenticated') {
    if (currentPath.startsWith('/login')) return null
    return `/login?next=${encodeURIComponent(currentPath)}`
  }
  if (error.status === 403 && error.code === 'forbidden') return '/forbidden'
  return null
}

/** `next` an toàn: chỉ đường dẫn nội bộ (bắt đầu bằng một dấu `/`), không phải URL ngoài. */
export function safeNext(next: string | null, fallback = '/home'): string {
  if (!next || !next.startsWith('/') || next.startsWith('//')) return fallback
  return next
}
