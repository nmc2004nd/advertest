import { describe, expect, it } from 'vitest'

import { PENDING_SCREENS, pendingScreen } from '@/auth/pending-screens'
import { expectLabelledControls, render } from '@/test-utils'

import { LandingPage } from './LandingPage'
import { LoginPage } from './LoginPage'
import { PendingPage } from './PendingPage'
import { RequestAccessPage, RequestAccessSentPage } from './RequestAccessPage'
import { ResetPasswordPage } from './ResetPasswordPage'

describe('trang công khai', () => {
  it('giới thiệu có ba role và hai nút', () => {
    const html = render(<LandingPage />)
    expect(html).toContain('href="/request-access"')
    expect(html).toContain('href="/login"')
    expect(html).toContain('Kỹ sư an toàn (reviewer)')
  })

  it('đăng nhập có email, mật khẩu có nhãn', () => {
    expectLabelledControls(render(<LoginPage />, '/login?next=/admin/users'), 2)
  })

  it('yêu cầu truy cập có đủ 7 ô nhập có nhãn', () => {
    const html = render(<RequestAccessPage />)
    expectLabelledControls(html, 7)
    expect(html).toContain('Quản trị viên')
  })

  it('màn hình xác nhận không nhắc email đã tồn tại hay chưa', () => {
    const html = render(<RequestAccessSentPage />)
    expect(html).toContain('đã được ghi nhận')
    expect(html).not.toMatch(/đã tồn tại/)
  })
})

describe('/pending', () => {
  it.each([
    ['account_pending', 'đang chờ duyệt'],
    ['account_rejected', 'bị từ chối'],
    ['account_disabled', 'bị vô hiệu hóa'],
  ])('mã %s', (code, text) => {
    expect(render(<PendingPage />, `/pending?code=${code}`)).toContain(text)
  })

  it('mã lạ hoặc thiếu thì hiển thị đang chờ duyệt', () => {
    expect(pendingScreen('forbidden')).toBe(PENDING_SCREENS.account_pending)
    expect(pendingScreen(null)).toBe(PENDING_SCREENS.account_pending)
  })
})

describe('/reset-password/:token', () => {
  it('hai ô mật khẩu có nhãn', () => {
    expectLabelledControls(render(<ResetPasswordPage />, '/reset-password/abc'), 2)
  })
})
