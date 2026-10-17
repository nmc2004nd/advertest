import { describe, expect, it } from 'vitest'

import { demoAccount } from './demo-account'

describe('demoAccount', () => {
  it('trả về tài khoản khi có đủ email và mật khẩu', () => {
    expect(
      demoAccount({ VITE_DEMO_EMAIL: ' demo@advertest.vn ', VITE_DEMO_PASSWORD: 'pw' }),
    ).toEqual({ email: 'demo@advertest.vn', password: 'pw' })
  })

  it('ẩn khi thiếu một trong hai biến', () => {
    expect(demoAccount({})).toBeNull()
    expect(demoAccount({ VITE_DEMO_EMAIL: 'demo@advertest.vn' })).toBeNull()
    expect(demoAccount({ VITE_DEMO_EMAIL: ' ', VITE_DEMO_PASSWORD: 'pw' })).toBeNull()
  })
})
