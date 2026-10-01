import { describe, expect, it } from 'vitest'

import { listMocks } from '@/api/mocks'
import type {
  AttackSpecAdminPage,
  EstimateResponse,
  ExperimentClone,
  ExperimentDetail,
} from '@/contracts/api'

import { catalogPreset, PATCH_PRESET_LEVELS } from './levels'

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
  STORAGE_KEY,
  trainingSummary,
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
  attacks: [
    {
      attackSpecId: 'a',
      specSha256: 'sha',
      levels: [4],
      requiresTraining: false,
      trainingSliceId: null,
    },
  ],
}

/** Cấu hình đủ, có thêm một attack cần train (patch). */
const WITH_PATCH: Draft = {
  ...FULL,
  attacks: [
    ...FULL.attacks,
    {
      attackSpecId: 'p',
      specSha256: 'sp',
      levels: [0.1],
      requiresTraining: true,
      trainingSliceId: null,
    },
  ],
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
    const added = reducer(FULL, {
      type: 'toggleAttack',
      attackSpecId: 'b',
      specSha256: 'sb',
      requiresTraining: false,
    })
    expect(added.attacks.map((a) => a.attackSpecId)).toEqual(['a', 'b'])
    const levels = reducer(added, { type: 'levels', attackSpecId: 'b', levels: [2, 8] })
    expect(levels.attacks[1].levels).toEqual([2, 8])
    const removed = reducer(levels, {
      type: 'toggleAttack',
      attackSpecId: 'a',
      specSha256: 'sha',
      requiresTraining: false,
    })
    expect(removed.attacks.map((a) => a.attackSpecId)).toEqual(['b'])
  })
})

describe('điều kiện sang bước sau', () => {
  it.each([
    [1, { protocolId: null }, false],
    [2, { modelId: null }, false],
    [3, { mappingId: null }, false],
    [4, { attacks: [] }, false],
    [4, { attacks: [{ ...FULL.attacks[0], levels: [] }] }, false],
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
    const withB = reducer(FULL, {
      type: 'toggleAttack',
      attackSpecId: 'b',
      specSha256: 'sb',
      requiresTraining: false,
    })
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
    store.setItem(STORAGE_KEY, '{hỏng')
    expect(loadDraft(store)).toEqual(EMPTY_DRAFT)
  })

  it('Phase 6: nháp v1 cũ bị bỏ qua (khóa mới v2)', () => {
    const store = new MemoryStore()
    store.setItem(
      'advertest.wizard.v1',
      JSON.stringify({ ...FULL, attacks: [{ attackSpecId: 'a' }] }),
    )
    expect(STORAGE_KEY).toBe('advertest.wizard.v2')
    expect(loadDraft(store)).toEqual(EMPTY_DRAFT)
  })

  it('Phase 6: attack trong nháp thiếu trường mới được điền mặc định', () => {
    const store = new MemoryStore()
    const old = { ...FULL, attacks: [{ attackSpecId: 'a', specSha256: 'sha', levels: [4] }] }
    store.setItem(STORAGE_KEY, JSON.stringify(old))
    expect(loadDraft(store).attacks).toEqual(FULL.attacks)
    expect(canAdvance(loadDraft(store))).toBe(true)
  })
})

describe('Phase 6: slice huấn luyện và dừng sớm', () => {
  it('attack cần train chặn bước 4 và không dựng body cho tới khi chọn slice huấn luyện', () => {
    expect(canAdvance(WITH_PATCH)).toBe(false)
    expect(buildBody(WITH_PATCH)).toBeNull()
    const chosen = reducer(WITH_PATCH, { type: 'trainingSlice', attackSpecId: 'p', id: 'ts' })
    expect(canAdvance(chosen)).toBe(true)
    const body = buildBody(chosen)
    expect(body?.attacks[1]).toMatchObject({ training_slice_id: 'ts', grid: { levels: [0.1] } })
    expect(body?.attacks[0]).not.toHaveProperty('training_slice_id')
  })

  it('đổi slice đánh giá hoặc dataset version thì phải chọn lại slice huấn luyện', () => {
    const chosen = reducer(
      { ...WITH_PATCH, step: 3 },
      { type: 'trainingSlice', attackSpecId: 'p', id: 'ts' },
    )
    expect(reducer(chosen, { type: 'slice', id: 's' }).attacks[1].trainingSliceId).toBe('ts')
    expect(reducer(chosen, { type: 'slice', id: 's2' }).attacks[1].trainingSliceId).toBeNull()
    expect(
      reducer(chosen, { type: 'datasetVersion', id: 'dv2' }).attacks[1].trainingSliceId,
    ).toBeNull()
  })

  it('dừng sớm bật mặc định: body như Phase 5; tắt thì mọi attack có early_stop = false', () => {
    expect(EMPTY_DRAFT.earlyStop).toBe(true)
    expect(buildBody(FULL)?.attacks[0].grid).toEqual({ levels: [4] })
    const off = reducer(FULL, { type: 'earlyStop', on: false })
    expect(buildBody(off)?.attacks[0].grid).toEqual({ levels: [4], early_stop: false })
  })

  it('preset "Toàn bộ catalog": mọi spec, patch 0.1 và 0.25, giữ slice huấn luyện đã chọn', () => {
    const page = listMocks<AttackSpecAdminPage>('attack_spec_admin_page')[0]
    const specs = page.items.filter((spec) => spec.is_active)
    const preset = catalogPreset(specs)
    expect(preset).toHaveLength(specs.length)
    const patch = specs.find((spec) => spec.requires_training)
    if (!patch) throw new Error('Thiếu spec patch trong mock')
    expect(preset.find((a) => a.attackSpecId === patch.id)?.levels).toEqual(PATCH_PRESET_LEVELS)
    for (const spec of specs.filter((s) => s.primary_param.type === 'discrete')) {
      expect(preset.find((a) => a.attackSpecId === spec.id)?.levels).toEqual(
        spec.primary_param.values,
      )
    }
    // Dưới trần 50 run mỗi experiment (backend `MAX_RUNS`).
    expect(preset.reduce((n, a) => n + a.levels.length, 0)).toBeLessThanOrEqual(50)

    const before = reducer(
      { ...FULL, attacks: [] },
      {
        type: 'toggleAttack',
        attackSpecId: patch.id,
        specSha256: patch.spec_sha256,
        requiresTraining: true,
      },
    )
    const kept = reducer(
      reducer(before, { type: 'trainingSlice', attackSpecId: patch.id, id: 'ts' }),
      { type: 'preset', attacks: preset },
    )
    expect(kept.attacks.find((a) => a.attackSpecId === patch.id)?.trainingSliceId).toBe('ts')
  })

  it('nhân bản giữ slice huấn luyện và dừng sớm', () => {
    const detail = listMocks<ExperimentDetail>('experiment_detail').find((d) =>
      d.config.attacks.some((a) => a.training_slice_id),
    )
    if (!detail) throw new Error('Thiếu mock experiment có patch')
    const draft = draftFromClone(detail.config, [], 'dv')
    const patch = draft.attacks.find((a) => a.requiresTraining)
    expect(patch?.trainingSliceId).toBe(
      detail.config.attacks.find((a) => a.training_slice_id)?.training_slice_id,
    )
    const stops = detail.config.attacks.map((a) => a.grid?.early_stop !== false)
    expect(draft.earlyStop).toBe(stops.every(Boolean))
    expect(draft.earlyStopMixed).toBe(stops.some(Boolean) && !stops.every(Boolean))

    const mixed = draftFromClone(
      {
        ...detail.config,
        attacks: detail.config.attacks.map((a, i) =>
          a.grid ? { ...a, grid: { ...a.grid, early_stop: i !== 0 } } : a,
        ),
      },
      [],
      'dv',
    )
    expect([mixed.earlyStop, mixed.earlyStopMixed]).toEqual([false, true])
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

describe('Phase 6: thời gian train trong ước lượng (task 31)', () => {
  const estimate = listMocks<EstimateResponse>('estimate_response').find((e) =>
    e.runs.some((r) => r.training_seconds),
  )
  if (!estimate) throw new Error('Thiếu mock ước lượng có training_seconds')
  const patchId = estimate.runs.find((r) => r.training_seconds)?.attack_spec_id ?? ''

  it('cộng training_seconds của các patch chưa có', () => {
    const total = estimate.runs
      .filter((r) => r.attack_spec_id === patchId)
      .reduce((sum, r) => sum + (r.training_seconds ?? 0), 0)
    const count = estimate.runs.filter((r) => r.attack_spec_id === patchId && r.training_seconds)
    expect(trainingSummary(estimate, patchId)).toBe(
      `Thời gian train: ${formatDuration(total)} (${count.length} patch cần train)`,
    )
  })

  it('patch đã có, hoặc chưa đo được trên máy này', () => {
    const ready: EstimateResponse = {
      ...estimate,
      runs: estimate.runs.map((r) => ({ ...r, training_seconds: null })),
    }
    expect(trainingSummary(ready, patchId)).toBe('Patch đã có sẵn: không cần train.')
    const missing: EstimateResponse = { ...ready, missing_profiles: [patchId] }
    expect(trainingSummary(missing, patchId)).toContain('Chưa đo được thời gian train')
  })
})
