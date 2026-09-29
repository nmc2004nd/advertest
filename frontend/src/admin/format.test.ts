import { describe, expect, it } from 'vitest'

import { actionLabel, dayRangeToUtc, describeChange, middleTruncate } from './format'

describe('middleTruncate', () => {
  it('rút gọn ở giữa, giữ đầu và cuối', () => {
    expect(middleTruncate('0f6d2c3e-8a41-4b7d-9c5e-1a2b3c4d5e01')).toBe('0f6d2c3e…5e01')
    expect(middleTruncate('ngan')).toBe('ngan')
  })
})

describe('describeChange', () => {
  it('chỉ liệt kê trường thay đổi', () => {
    expect(
      describeChange({
        before: { status: 'pending', roles: [] },
        after: { status: 'active', roles: ['engineer'] },
      }),
    ).toEqual(['roles: [] → [engineer]', 'status: pending → active'])
    expect(
      describeChange({
        before: { status: 'active', roles: [] },
        after: { status: 'active', roles: [] },
      }),
    ).toEqual([])
    expect(describeChange({ before: null, after: { status: 'pending' } })).toEqual([
      'status: pending',
    ])
  })
})

describe('dayRangeToUtc', () => {
  it('ngày kết thúc tính trọn ngày (until = đầu ngày sau)', () => {
    const { since, until } = dayRangeToUtc('2026-09-01', '2026-09-01')
    expect(since && until && new Date(until).getTime() - new Date(since).getTime()).toBe(
      24 * 3600 * 1000,
    )
    expect(dayRangeToUtc('', '')).toEqual({})
  })
})

describe('actionLabel', () => {
  it('nhãn tiếng Việt cho action đã biết, giữ nguyên action lạ', () => {
    expect(actionLabel('user.approved')).toBe('Duyệt tài khoản')
    expect(actionLabel('x')).toBe('x')
  })
})
