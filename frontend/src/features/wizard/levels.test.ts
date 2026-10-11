import { describe, expect, it } from 'vitest'

import type { PrimaryParam } from '@/contracts/api'

import {
  addLevel,
  levelCandidates,
  levelLabel,
  MAX_LEVELS,
  presetLevels,
  rangeText,
} from './levels'

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

describe('chip level (Phase R3: chọn bằng chip, không gõ số)', () => {
  const spec = (primary_param: PrimaryParam, labels: Record<string, string> = {}) => ({
    primary_param,
    requires_training: false,
    metadata: { level_labels: labels },
  })

  it('gồm level đang chọn, level có nhãn và bộ gợi ý, sắp tăng dần, không trùng', () => {
    expect(levelCandidates(spec(EPS, { '2': 'rất nhẹ' }), [3, 8])).toEqual([2, 3, 4, 8, 16, 32])
  })

  it('rời rạc: mọi giá trị; nhãn ngoài dải bị bỏ', () => {
    expect(levelCandidates(spec(SEVERITY, { '9': 'ngoài dải' }), [2])).toEqual([1, 2, 3, 4, 5])
  })

  it('không quá MAX_LEVELS chip, trừ level đang chọn', () => {
    const many = Object.fromEntries(Array.from({ length: 20 }, (_, i) => [String(i + 1), 'x']))
    expect(levelCandidates(spec(EPS, many), [])).toHaveLength(MAX_LEVELS)
  })

  it('nhãn so theo giá trị số', () => {
    expect(levelLabel({ level_labels: { '1.0': 'lất phất' } }, 1)).toBe('lất phất')
    expect(levelLabel({ level_labels: {} }, 1)).toBeNull()
    expect(levelLabel(null, 1)).toBeNull()
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
