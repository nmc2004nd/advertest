import { describe, expect, it } from 'vitest'

import type { PrimaryParam } from '@/contracts/api'

import { addLevel, levelError, MAX_LEVELS, presetLevels, rangeText } from './levels'

const EPS: PrimaryParam = {
  name: 'eps',
  type: 'continuous',
  min: 0,
  max: 32,
  values: null,
  unit: '1/255',
}
const L2: PrimaryParam = {
  name: 'eps',
  type: 'continuous',
  min: 0,
  max: 1.5,
  values: null,
  unit: 'L2',
}
const SEVERITY: PrimaryParam = {
  name: 'severity',
  type: 'discrete',
  min: 1,
  max: 5,
  values: [1, 2, 3, 4, 5],
  unit: '',
}

describe('chip level (validation.md: từ chối giá trị ngoài dải và giá trị trùng)', () => {
  it('nhận giá trị trong dải', () => {
    expect(levelError(EPS, [2], '4')).toBeNull()
    expect(levelError(EPS, [], '0')).toBeNull()
    expect(levelError(EPS, [], '32')).toBeNull()
    expect(levelError(L2, [], '0,5')).toBeNull() // dấu phẩy thập phân
  })

  it('từ chối giá trị ngoài dải', () => {
    expect(levelError(EPS, [], '40')).toBe('Level 40 ngoài dải 0–32 1/255')
    expect(levelError(EPS, [], '-1')).toContain('ngoài dải')
  })

  it('từ chối giá trị trùng', () => {
    expect(levelError(EPS, [2, 4], '4')).toBe('Level 4 đã có')
    expect(levelError(EPS, [2, 4], '4.0')).toBe('Level 4 đã có')
  })

  it('từ chối chữ, ô trống và quá 12 level', () => {
    expect(levelError(EPS, [], 'abc')).toContain('không phải là số')
    expect(levelError(EPS, [], '  ')).toBe('Nhập một giá trị')
    const full = Array.from({ length: MAX_LEVELS }, (_, i) => i + 1)
    expect(levelError(EPS, full, '20')).toBe('Tối đa 12 level mỗi attack')
  })

  it('spec rời rạc chỉ nhận giá trị trong danh sách', () => {
    expect(levelError(SEVERITY, [], '3')).toBeNull()
    expect(levelError(SEVERITY, [], '2.5')).toBe('Level 2.5 ngoài dải 1, 2, 3, 4, 5')
  })

  it('giữ thứ tự tăng dần', () => {
    expect(addLevel([2, 8], 4)).toEqual([2, 4, 8])
  })
})

describe('preset', () => {
  it('eps 1/255: 2, 4, 8, 16... trong dải', () => {
    expect(presetLevels(EPS)).toEqual([4, 8, 16, 32])
    expect(presetLevels({ ...EPS, max: 16 })).toEqual([2, 4, 8, 16])
  })

  it('dải nhỏ: 4 điểm chia đều', () => {
    expect(presetLevels(L2)).toEqual([0.375, 0.75, 1.125, 1.5])
  })

  it('rời rạc: mọi giá trị', () => {
    expect(presetLevels(SEVERITY)).toEqual([1, 2, 3, 4, 5])
    expect(rangeText(SEVERITY)).toBe('1, 2, 3, 4, 5')
  })
})
