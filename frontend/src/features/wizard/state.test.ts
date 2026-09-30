import { describe, expect, it } from 'vitest'

import { listMocks } from '@/api/mocks'
import type { ExperimentClone } from '@/contracts/api'

import {
  buildBody,
  canAdvance,
  clearDraft,
  type Draft,
  draftFromClone,
  EMPTY_DRAFT,
  formatDuration,
  groupFieldErrors,
  hasLevelInputError,
  loadDraft,
  reducer,
  saveDraft,
  SEED,
  type Step,
  stepOfField,
} from './state'

const FULL: Draft = {
  ...EMPTY_DRAFT,
  step: 4,
  protocolId: 'p',
  modelId: 'm',
  datasetVersionId: 'dv',
  sliceId: 's',
  mappingId: 'map',
  targetId: 't',
  limitSeconds: 7200,
  attacks: [{ attackSpecId: 'a', specSha256: 'sha', levels: [4] }],
}

class MemoryStore {
  data = new Map<string, string>()
  getItem = (k: string) => this.data.get(k) ?? null
  setItem = (k: string, v: string) => void this.data.set(k, v)
  removeItem = (k: string) => void this.data.delete(k)
}

describe('reducer', () => {
  it('đổi model thì bỏ class mapping; đổi dataset version thì bỏ slice và mapping', () => {
    const byModel = reducer(FULL, { type: 'model', id: 'm2' })
    expect([byModel.modelId, byModel.mappingId, byModel.sliceId]).toEqual(['m2', null, 's'])
    const byVersion = reducer(FULL, { type: 'datasetVersion', id: 'dv2' })
    expect([byVersion.sliceId, byVersion.mappingId]).toEqual([null, null])
    expect(reducer(FULL, { type: 'model', id: 'm' })).toBe(FULL) // chọn lại cùng model: giữ nguyên
  })

  it('chọn target đặt giới hạn mặc định của target', () => {
    const next = reducer(FULL, { type: 'target', id: 't2', defaultLimitSeconds: 3600 })
    expect([next.targetId, next.limitSeconds]).toEqual(['t2', 3600])
  })

  it('bật tắt attack và sửa level', () => {
    const added = reducer(FULL, { type: 'toggleAttack', attackSpecId: 'b', specSha256: 'sb' })
    expect(added.attacks.map((a) => a.attackSpecId)).toEqual(['a', 'b'])
    const levels = reducer(added, { type: 'levels', attackSpecId: 'b', levels: [2, 8] })
    expect(levels.attacks[1].levels).toEqual([2, 8])
    const removed = reducer(levels, { type: 'toggleAttack', attackSpecId: 'a', specSha256: 'sha' })
    expect(removed.attacks.map((a) => a.attackSpecId)).toEqual(['b'])
  })
})

describe('điều kiện sang bước sau', () => {
  it.each([
    [1, { protocolId: null }, false],
    [2, { modelId: null }, false],
    [3, { mappingId: null }, false],
    [4, { attacks: [] }, false],
    [4, { attacks: [{ attackSpecId: 'a', specSha256: 's', levels: [] }] }, false],
    [5, { limitSeconds: 0 }, false],
  ] satisfies [Step, Partial<Draft>, boolean][])(
    'bước %i thiếu dữ liệu thì chặn',
    (step, change, expected) => {
      expect(canAdvance({ ...FULL, ...change, step })).toBe(expected)
    },
  )

  it('bước 4 có level sai đang nhập thì chặn (validation.md: không sang bước tiếp)', () => {
    expect(canAdvance(FULL)).toBe(true)
    expect(canAdvance(FULL, { levelInputError: true })).toBe(false)
  })

  it('bước 5: giới hạn không vượt max của target', () => {
    const step5 = { ...FULL, step: 5 as const }
    expect(canAdvance(step5, { maxLimitSeconds: 7200 })).toBe(true)
    expect(canAdvance(step5, { maxLimitSeconds: 3600 })).toBe(false)
  })
})

describe('lỗi ô nhập level (review Group 5 #1)', () => {
  it('chỉ tính attack đang chọn: bỏ chọn attack có lỗi thì không còn chặn', () => {
    const errors = { a: false, b: true }
    expect(hasLevelInputError(FULL.attacks, errors)).toBe(false) // chỉ còn attack "a"
    const withB = reducer(FULL, { type: 'toggleAttack', attackSpecId: 'b', specSha256: 'sb' })
    expect(hasLevelInputError(withB.attacks, errors)).toBe(true)
  })
})

describe('body gửi lên', () => {
  it('đủ cấu hình: grid, seed 0, giới hạn thời gian, tên bỏ trống là null', () => {
    const body = buildBody({ ...FULL, name: '  ' })
    expect(body).not.toBeNull()
    expect(body?.attacks[0]).toMatchObject({ mode: 'grid', grid: { levels: [4] }, seed: SEED })
    expect(body?.limit).toEqual({ kind: 'time', value: '7200' })
    expect(body?.name).toBeNull()
  })

  it('thiếu gì cũng không dựng body (không gọi ước lượng)', () => {
    expect(buildBody({ ...FULL, targetId: null })).toBeNull()
    expect(buildBody({ ...FULL, attacks: [] })).toBeNull()
  })
})

describe('lỗi 422 theo bước', () => {
  it('đường dẫn trường → bước', () => {
    expect(stepOfField('protocol_id')).toBe(1)
    expect(stepOfField('model_version_id')).toBe(2)
    expect(stepOfField('class_mapping_id')).toBe(3)
    expect(stepOfField('attacks.0.grid.levels')).toBe(4)
    expect(stepOfField('limit.value')).toBe(5)
    expect(stepOfField('cloned_from')).toBe(6)
  })

  it('gom lỗi, bước sớm nhất', () => {
    const { byPath, firstStep } = groupFieldErrors([
      { path: 'limit.value', message: 'Quá giới hạn' },
      { path: 'attacks.0.grid.levels', message: 'Ngoài dải' },
      { path: 'attacks.0.grid.levels', message: 'Trùng' },
    ])
    expect(firstStep).toBe(4)
    expect(byPath['attacks.0.grid.levels']).toBe('Ngoài dải; Trùng')
  })
})

describe('nháp trong sessionStorage', () => {
  it('lưu, đọc lại, xóa', () => {
    const store = new MemoryStore()
    saveDraft(FULL, store)
    expect(loadDraft(store)).toEqual(FULL)
    clearDraft(store)
    expect(loadDraft(store)).toEqual(EMPTY_DRAFT)
  })

  it('dữ liệu hỏng thì bắt đầu lại', () => {
    const store = new MemoryStore()
    store.setItem('advertest.wizard.v1', '{hỏng')
    expect(loadDraft(store)).toEqual(EMPTY_DRAFT)
  })
})

describe('nhân bản', () => {
  it('điền sẵn và mở bước 6 kèm cảnh báo', () => {
    const clone = listMocks<ExperimentClone>('experiment_clone').find((c) => c.warnings.length > 0)
    if (!clone) throw new Error('Thiếu mock clone có cảnh báo')
    const draft = draftFromClone(clone.config, clone.warnings, 'dv')
    expect(draft.step).toBe(6)
    expect(draft.clonedFrom).toBe(clone.config.cloned_from)
    expect(draft.attacks).toHaveLength(clone.config.attacks.length)
    expect(draft.cloneWarnings).toEqual(clone.warnings)
    expect(buildBody(draft)?.cloned_from).toBe(clone.config.cloned_from)
  })
})

it('định dạng thời gian', () => {
  expect(formatDuration(null)).toBe('—')
  expect(formatDuration(42)).toBe('42 giây')
  expect(formatDuration(1500)).toBe('25 phút')
  expect(formatDuration(7200)).toBe('2 giờ')
  expect(formatDuration(5460)).toBe('1 giờ 31 phút')
})
