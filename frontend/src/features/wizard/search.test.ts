import { describe, expect, it } from 'vitest'

import { listMocks } from '@/api/mocks'
import type { AttackConfig, components } from '@/contracts/api'

import {
  defaultSearch,
  defaultTol,
  fromSearchConfig,
  searchErrors,
  type SearchDraft,
  searchSchema,
  targetClassesOf,
  toSearchConfig,
} from './search'

type PrimaryParam = components['schemas']['PrimaryParam']

const EPS: PrimaryParam = {
  name: 'eps',
  type: 'continuous',
  min: 0,
  max: 32,
  values: null,
  unit: '1/255',
}
const SEVERITY: PrimaryParam = {
  name: 'severity',
  type: 'discrete',
  min: 1,
  max: 5,
  values: [1, 2, 3, 4, 5],
  unit: '',
}
const CLASSES = ['car', 'person']

const valid = (patch: Partial<SearchDraft> = {}, param = EPS): SearchDraft => ({
  ...defaultSearch(param, 300),
  ...patch,
})

describe('defaultSearch', () => {
  it('dải của spec, tol = (hi − lo) / 256, relative_drop 20%, mặc định của contract', () => {
    expect(defaultSearch(EPS, 300)).toEqual({
      thresholdKind: 'relative_drop',
      threshold: 0.2,
      classFilter: null,
      lo: 0,
      hi: 32,
      tol: 0.125,
      coarseN: 4,
      subsetSize: 100,
      bootstrapSamples: 200,
    })
    expect(defaultTol(1, 5)).toBe(4 / 256)
  })

  it('tập con không lớn hơn slice (API từ chối), tối thiểu 2', () => {
    expect(defaultSearch(EPS, 30).subsetSize).toBe(30)
    expect(defaultSearch(EPS, 1).subsetSize).toBe(2)
    expect(defaultSearch(EPS, null).subsetSize).toBe(100)
  })

  it('mặc định hợp lệ với cả tham số liên tục và rời rạc', () => {
    expect(searchErrors(valid(), EPS, 300, CLASSES)).toEqual({})
    expect(searchErrors(valid({}, SEVERITY), SEVERITY, 300, CLASSES)).toEqual({})
  })
})

describe('searchSchema: từ chối đúng các trường hợp backend từ chối', () => {
  const cases: [string, Partial<SearchDraft>, keyof SearchDraft][] = [
    ['ngưỡng 0', { threshold: 0 }, 'threshold'],
    ['ngưỡng > 100%', { threshold: 1.01 }, 'threshold'],
    ['ngưỡng trống', { threshold: Number.NaN }, 'threshold'],
    ['lo dưới dải spec', { lo: -1 }, 'lo'],
    ['hi trên dải spec', { hi: 33 }, 'hi'],
    ['lo ≥ hi', { lo: 10, hi: 10 }, 'hi'],
    ['tol = 0', { tol: 0 }, 'tol'],
    ['tol ≥ hi − lo', { lo: 0, hi: 1, tol: 1 }, 'tol'],
    ['coarse_n < 3', { coarseN: 2 }, 'coarseN'],
    ['coarse_n > 8', { coarseN: 9 }, 'coarseN'],
    ['coarse_n lẻ', { coarseN: 3.5 }, 'coarseN'],
    ['tập con < 2', { subsetSize: 1 }, 'subsetSize'],
    ['tập con lớn hơn slice', { subsetSize: 301 }, 'subsetSize'],
    ['bootstrap âm', { bootstrapSamples: -1 }, 'bootstrapSamples'],
    ['bootstrap > 1000', { bootstrapSamples: 1001 }, 'bootstrapSamples'],
    ['class không phải class đích', { classFilter: 'dog' }, 'classFilter'],
  ]
  it.each(cases)('%s', (_, patch, field) => {
    const errors = searchErrors(valid(patch), EPS, 300, CLASSES)
    expect(Object.keys(errors)).toContain(field)
  })

  it('tham số rời rạc: lo/hi phải là giá trị của spec, không kiểm tra tol', () => {
    expect(searchErrors(valid({ lo: 1.5 }, SEVERITY), SEVERITY, 300, CLASSES).lo).toBeDefined()
    expect(searchErrors(valid({ lo: 4, hi: 5, tol: 1 }, SEVERITY), SEVERITY, 300, CLASSES)).toEqual(
      {},
    )
  })

  it('chấp nhận biên: ngưỡng 100%, coarse_n 3 và 8, bootstrap 0 và 1000, tập con bằng slice', () => {
    for (const patch of [
      { threshold: 1 },
      { coarseN: 3 },
      { coarseN: 8 },
      { bootstrapSamples: 0 },
      { bootstrapSamples: 1000 },
      { subsetSize: 300 },
      { classFilter: 'person' },
    ]) {
      expect(searchSchema(EPS, 300, CLASSES).safeParse(valid(patch)).success).toBe(true)
    }
  })

  it('chưa biết slice hay mapping thì để backend kiểm tra', () => {
    expect(searchErrors(valid({ subsetSize: 5000, classFilter: 'x' }), EPS, null, null)).toEqual({})
  })
})

describe('chuyển đổi SearchConfig', () => {
  it('khứ hồi với mock của contract', () => {
    const configs = listMocks<AttackConfig>('attack_config').filter((c) => c.search)
    expect(configs.length).toBeGreaterThan(0)
    for (const config of configs) {
      const search = config.search
      if (!search) throw new Error('mock thiếu search')
      expect(toSearchConfig(fromSearchConfig(search))).toEqual({
        ...search,
        class_filter: search.class_filter ?? null,
      })
    }
  })

  it('class đích: bỏ null, không trùng, sắp xếp', () => {
    expect(targetClassesOf({ a: 'person', b: null, c: 'car', d: 'person' })).toEqual([
      'car',
      'person',
    ])
  })
})
