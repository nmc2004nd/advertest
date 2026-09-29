import { describe, expect, it } from 'vitest'

import { expectLabelledControls, render } from '@/test-utils'

import { LandingPage } from './LandingPage'
import { LoginPage } from './LoginPage'
import { RequestAccessPage, RequestAccessSentPage } from './RequestAccessPage'

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
