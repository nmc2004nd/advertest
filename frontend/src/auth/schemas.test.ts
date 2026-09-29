import { describe, expect, it } from 'vitest'

import { accessRequestSchema, passwordChangeSchema, passwordResetSchema } from './schemas'

const valid = {
  full_name: 'Trần Thị Bích',
  email: 'bich@example.com',
  organization: '',
  requested_role: 'engineer',
  reason: 'Kiểm thử model',
  password: 'mat-khau-du-dai',
  password_confirm: 'mat-khau-du-dai',
}

function errorPaths(result: { success: boolean; error?: { issues: { path: PropertyKey[] }[] } }) {
  return result.success ? [] : (result.error?.issues ?? []).map((i) => i.path.join('.'))
}

describe('accessRequestSchema (validation.md: form yêu cầu truy cập)', () => {
  it('nhận dữ liệu hợp lệ', () => {
    expect(accessRequestSchema.safeParse(valid).success).toBe(true)
  })

  it('từ chối mật khẩu dưới 10 ký tự', () => {
    const result = accessRequestSchema.safeParse({
      ...valid,
      password: '123456789',
      password_confirm: '123456789',
    })
    expect(errorPaths(result)).toContain('password')
  })

  it('từ chối mật khẩu trùng email (không phân biệt hoa thường)', () => {
    const result = accessRequestSchema.safeParse({
      ...valid,
      password: 'BICH@example.com',
      password_confirm: 'BICH@example.com',
    })
    expect(errorPaths(result)).toContain('password')
  })

  it('từ chối mật khẩu nhập lại không khớp, email sai, thiếu lý do, role lạ', () => {
    expect(
      errorPaths(accessRequestSchema.safeParse({ ...valid, password_confirm: 'khac' })),
    ).toEqual(['password_confirm'])
    expect(errorPaths(accessRequestSchema.safeParse({ ...valid, email: 'khong-hop-le' }))).toEqual([
      'email',
    ])
    expect(errorPaths(accessRequestSchema.safeParse({ ...valid, reason: '  ' }))).toEqual([
      'reason',
    ])
    expect(errorPaths(accessRequestSchema.safeParse({ ...valid, requested_role: 'root' }))).toEqual(
      ['requested_role'],
    )
  })
})

describe('đổi và đặt lại mật khẩu', () => {
  it('mật khẩu mới ≥ 10 ký tự và nhập lại khớp', () => {
    expect(
      errorPaths(
        passwordChangeSchema.safeParse({
          current_password: 'x',
          new_password: 'ngan',
          new_password_confirm: 'ngan',
        }),
      ),
    ).toEqual(['new_password'])
    expect(
      errorPaths(
        passwordResetSchema.safeParse({
          new_password: 'mat-khau-du-dai',
          new_password_confirm: 'mat-khau-khac-nhau',
        }),
      ),
    ).toEqual(['new_password_confirm'])
  })
})
