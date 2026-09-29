import { describe, expect, it } from 'vitest'

import { authRedirect, safeNext } from './auth-redirect'
import { ApiError } from './errors'

describe('authRedirect', () => {
  it('401 unauthenticated → /login kèm trang hiện tại', () => {
    const error = new ApiError(401, 'unauthenticated', 'x')
    expect(authRedirect(error, '/admin/users?tab=all')).toBe(
      '/login?next=%2Fadmin%2Fusers%3Ftab%3Dall',
    )
    expect(authRedirect(error, '/login')).toBeNull()
  })

  it('403 forbidden → /forbidden', () => {
    expect(authRedirect(new ApiError(403, 'forbidden', 'x'), '/admin/users')).toBe('/forbidden')
  })

  it('mã khác để trang tự xử lý', () => {
    for (const [status, code] of [
      [401, 'invalid_credentials'],
      [403, 'account_pending'],
      [403, 'csrf_failed'],
      [429, 'rate_limited'],
    ] as const) {
      expect(authRedirect(new ApiError(status, code, 'x'), '/login')).toBeNull()
    }
    expect(authRedirect(new Error('x'), '/home')).toBeNull()
  })
})

describe('safeNext', () => {
  it('chỉ nhận đường dẫn nội bộ', () => {
    expect(safeNext('/admin/users')).toBe('/admin/users')
    expect(safeNext('//evil.com')).toBe('/home')
    expect(safeNext('https://evil.com')).toBe('/home')
    expect(safeNext(null)).toBe('/home')
  })
})
