import { describe, expect, it } from 'vitest'

import { listMocks } from '@/api/mocks'
import type { EstimateResponse, ExperimentClone, ExperimentDetail } from '@/contracts/api'

import { defaultSearch } from './search'

import {
  buildBody,
  canAdvance,
  clearDraft,
  type Draft,
  draftFromClone,
  draftKeyOf,
  draftRequest,
  EMPTY_DRAFT,
  estimateText,
  formatDuration,
  groupFieldErrors,
  hasLevelInputError,
  hasSearchInputError,
  loadDraft,
  reducer,
  runCounts,
  saveDraft,
  searchCostSummary,
  searchErrorKey,
  SEED,
  type Step,
  stepOfField,
  STORAGE_KEY,
  trainingSummary,
} from './state'

const FULL: Draft = {
  ...EMPTY_DRAFT,
  step: 3,
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
      mode: 'grid',
      search: null,
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
      mode: 'grid',
      search: null,
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
    [2, { mappingId: null }, false],
    [2, { targetId: null }, false],
    [2, { limitSeconds: 0 }, false],
    [3, { attacks: [] }, false],
    [3, { attacks: [{ ...FULL.attacks[0], levels: [] }] }, false],
  ] satisfies [Step, Partial<Draft>, boolean][])(
    'bước %i thiếu dữ liệu thì chặn',
    (step, change, expected) => {
      expect(canAdvance({ ...FULL, ...change, step })).toBe(expected)
    },
  )

  it('bước 3 có ô nâng cao sai đang nhập thì chặn (validation.md: không sang bước tiếp)', () => {
    expect(canAdvance(FULL)).toBe(true)
    expect(canAdvance(FULL, { levelInputError: true })).toBe(false)
  })

  it('bước 2: giới hạn không vượt max của target', () => {
    const step2 = { ...FULL, step: 2 as const }
    expect(canAdvance(step2, { maxLimitSeconds: 7200 })).toBe(true)
    expect(canAdvance(step2, { maxLimitSeconds: 3600 })).toBe(false)
  })

  it('bước 2: protocol bắt buộc spec cần train thì phải chọn slice huấn luyện', () => {
    const step2 = { ...FULL, step: 2 as const }
    expect(canAdvance(step2, { needsTrainingSlice: true })).toBe(false)
    const chosen = reducer(step2, { type: 'draftTrainingSlice', id: 'ts' })
    expect(canAdvance(chosen, { needsTrainingSlice: true })).toBe(true)
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
    expect(stepOfField('preset')).toBe(1)
    expect(stepOfField('model_version_id')).toBe(2)
    expect(stepOfField('class_mapping_id')).toBe(2)
    expect(stepOfField('training_slice_id')).toBe(2)
    expect(stepOfField('limit.value')).toBe(2)
    expect(stepOfField('attacks.0.grid.levels')).toBe(3)
    expect(stepOfField('cloned_from')).toBe(3)
  })

  it('gom lỗi, bước sớm nhất', () => {
    const { byPath, firstStep } = groupFieldErrors([
      { path: 'attacks.0.grid.levels', message: 'Ngoài dải' },
      { path: 'limit.value', message: 'Quá giới hạn' },
      { path: 'attacks.0.grid.levels', message: 'Trùng' },
    ])
    expect(firstStep).toBe(2)
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

  it('Phase R3: nháp v2 cũ (wizard 6 bước) bị bỏ qua (khóa mới v3)', () => {
    const store = new MemoryStore()
    store.setItem('advertest.wizard.v2', JSON.stringify({ ...FULL, step: 5 }))
    expect(STORAGE_KEY).toBe('advertest.wizard.v3')
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
      { ...WITH_PATCH, step: 2 },
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

describe('Phase R3: bản nháp từ POST /experiments/draft', () => {
  const clones = listMocks<ExperimentClone>('experiment_clone')
  const STEP2: Draft = { ...FULL, step: 2, attacks: [], draftKey: null }

  it('request: đủ bước 2 mới dựng; Khám phá gửi attack_spec_ids, Chính thức luôn null', () => {
    expect(draftRequest({ ...STEP2, sliceId: null })).toBeNull()
    expect(draftRequest(STEP2)).toEqual({
      protocol_id: 'p',
      preset: 'standard',
      model_version_id: 'm',
      slice_id: 's',
      class_mapping_id: 'map',
      compute_target_id: 't',
      limit: { kind: 'time', value: '7200' },
      attack_spec_ids: null,
      training_slice_id: null,
    })
    expect(draftRequest(STEP2, ['a', 'b'])?.attack_spec_ids).toEqual(['a', 'b'])
    const official = reducer(STEP2, { type: 'experimentMode', mode: 'official' })
    expect(draftRequest({ ...official, protocolId: 'p' }, ['a'])?.attack_spec_ids).toBeNull()
    const fast = reducer(STEP2, { type: 'preset', key: 'fast' })
    expect(draftRequest(fast)?.preset).toBe('fast')
  })

  it('khóa bản nháp bỏ qua attack_spec_ids; đổi lựa chọn bước 1–2 thì đổi khóa', () => {
    const base = draftRequest(STEP2)
    const withIds = draftRequest(STEP2, ['a'])
    if (!base || !withIds) throw new Error('Thiếu request')
    expect(draftKeyOf(withIds)).toBe(draftKeyOf(base))
    const other = draftRequest(reducer(STEP2, { type: 'preset', key: 'deep' }))
    if (!other) throw new Error('Thiếu request')
    expect(draftKeyOf(other)).not.toBe(draftKeyOf(base))
  })

  it('đổi mode thì chọn lại protocol và bỏ khóa của protocol cũ', () => {
    const locked = { ...STEP2, mode: 'official' as const, requiredFor: 'p', minSliceSize: 200 }
    const next = reducer(locked, { type: 'experimentMode', mode: 'exploration' })
    expect([next.protocolId, next.requiredFor, next.minSliceSize]).toEqual([null, null, null])
    expect(reducer(next, { type: 'experimentMode', mode: 'exploration' })).toBe(next)
  })

  it('chọn dataset và slice trong một ô: đổi version thì bỏ mapping', () => {
    const next = reducer(STEP2, { type: 'dataSlice', datasetVersionId: 'dv2', sliceId: 's2' })
    expect([next.datasetVersionId, next.sliceId, next.mappingId]).toEqual(['dv2', 's2', null])
    const same = reducer(STEP2, { type: 'dataSlice', datasetVersionId: 'dv', sliceId: 's3' })
    expect([same.sliceId, same.mappingId]).toEqual(['s3', 'map'])
  })

  it.each(clones.map((c, i) => [i, c] as const))(
    'config tạo qua wizard bằng config của bản nháp (mock %i): cùng config_sha256',
    (_, clone) => {
      const loaded = reducer(STEP2, { type: 'drafted', key: 'k', clone, merge: false })
      expect([loaded.step, loaded.draftKey]).toEqual([3, 'k'])
      expect(loaded.notes).toEqual(clone.notes ?? [])
      expect(loaded.cloneWarnings).toEqual(clone.warnings)
      const body = buildBody({
        ...loaded,
        protocolId: clone.config.protocol_id,
        modelId: clone.config.model_version_id,
        sliceId: clone.config.slice_id,
        mappingId: clone.config.class_mapping_id,
        targetId: clone.config.compute_target_id,
        limitSeconds: Number(clone.config.limit.value),
      })
      expect(body?.attacks).toEqual(clone.config.attacks)
      expect(body?.limit).toEqual(clone.config.limit)
    },
  )

  it('nâng lên chính thức: mở bước 3, giữ promoted_from và lưu ý slice nhỏ', () => {
    const promoted = clones.find((c) => c.config.promoted_from)
    if (!promoted) throw new Error('Thiếu mock nâng lên chính thức')
    const draft = draftFromClone(
      promoted.config,
      promoted.warnings,
      'dv',
      'official',
      promoted.notes ?? [],
    )
    expect([draft.step, draft.mode, draft.promotedFrom]).toEqual([
      3,
      'official',
      promoted.config.promoted_from,
    ])
    expect(draft.notes.map((n) => n.code)).toEqual(['slice_too_small'])
    expect(buildBody(draft)?.promoted_from).toBe(promoted.config.promoted_from)
    // Lùi về bước 2 rồi đi tiếp mà không đổi gì: giữ attack của bản nháp (không dựng lại).
    const request = draftRequest(draft)
    if (!request) throw new Error('Thiếu request')
    expect(draft.draftKey).toBe(draftKeyOf(request))
    expect(buildBody({ ...draft, promotedFrom: null })).not.toHaveProperty('promoted_from')
  })
})

describe('nhân bản', () => {
  it('điền sẵn và mở bước 3 kèm cảnh báo', () => {
    const clone = listMocks<ExperimentClone>('experiment_clone').find((c) => c.warnings.length > 0)
    if (!clone) throw new Error('Thiếu mock clone có cảnh báo')
    const draft = draftFromClone(clone.config, clone.warnings, 'dv')
    expect(draft.step).toBe(3)
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

const EPS = {
  name: 'eps',
  type: 'continuous' as const,
  min: 0,
  max: 32,
  values: null,
  unit: '1/255',
}

describe('Phase 7: tự tìm ngưỡng', () => {
  const SEARCH = defaultSearch(EPS, 300)
  const searching = reducer(FULL, {
    type: 'mode',
    attackSpecId: 'a',
    mode: 'search',
    defaults: SEARCH,
  })

  it('nháp lưu theo định dạng trước Phase 7 mở được: attack là quét lưới, không mất trường nào', () => {
    const store = new MemoryStore()
    const phase6 = {
      ...FULL,
      earlyStop: false,
      attacks: [
        {
          attackSpecId: 'a',
          specSha256: 'sha',
          levels: [4, 8],
          requiresTraining: true,
          trainingSliceId: 'ts',
        },
      ],
    }
    store.setItem(STORAGE_KEY, JSON.stringify(phase6))
    const loaded = loadDraft(store)
    expect(loaded).toEqual({
      ...phase6,
      attacks: [{ ...phase6.attacks[0], mode: 'grid', search: null }],
    })
    expect(buildBody(loaded)?.attacks[0]).toMatchObject({
      mode: 'grid',
      grid: { levels: [4, 8], early_stop: false },
      search: null,
      training_slice_id: 'ts',
    })
  })

  it('bật tìm ngưỡng điền mặc định; về quét lưới giữ cấu hình để bật lại không mất', () => {
    expect(searching.attacks[0]).toMatchObject({ mode: 'search', search: SEARCH })
    const edited = reducer(searching, { type: 'search', attackSpecId: 'a', patch: { coarseN: 6 } })
    const grid = reducer(edited, {
      type: 'mode',
      attackSpecId: 'a',
      mode: 'grid',
      defaults: SEARCH,
    })
    expect(grid.attacks[0].mode).toBe('grid')
    const back = reducer(grid, {
      type: 'mode',
      attackSpecId: 'a',
      mode: 'search',
      defaults: SEARCH,
    })
    expect(back.attacks[0].search?.coarseN).toBe(6)
  })

  it('attack cần train (patch) không chuyển được sang tìm ngưỡng', () => {
    const patched = reducer(WITH_PATCH, {
      type: 'mode',
      attackSpecId: 'p',
      mode: 'search',
      defaults: SEARCH,
    })
    expect(patched.attacks[1].mode).toBe('grid')
  })

  it('body: mode search, grid null, search theo contract, không có slice huấn luyện', () => {
    const attack = buildBody(searching)?.attacks[0]
    expect(attack).toEqual({
      schema_version: 1,
      attack_spec_id: 'a',
      spec_sha256: 'sha',
      mode: 'search',
      grid: null,
      search: {
        threshold_kind: 'relative_drop',
        threshold: 0.2,
        lo: 0,
        hi: 32,
        tol: 0.125,
        coarse_n: 4,
        subset_size: 100,
        class_filter: null,
        bootstrap_samples: 200,
      },
      seed: SEED,
    })
  })

  it('tìm ngưỡng không cần level; lỗi nhập của form tìm ngưỡng chặn bước 4', () => {
    const noLevels = { ...searching, attacks: [{ ...searching.attacks[0], levels: [] }] }
    expect(canAdvance(noLevels)).toBe(true)
    const bad = { [searchErrorKey('a')]: true }
    expect(hasLevelInputError(noLevels.attacks, bad)).toBe(true)
    // Lỗi của chế độ đang ẩn không chặn.
    expect(hasLevelInputError(FULL.attacks, bad)).toBe(false)
    expect(hasLevelInputError(noLevels.attacks, { a: true })).toBe(false)
  })

  it('form tìm ngưỡng có ô trống hoặc lỗi thì chưa dựng body, chưa ước lượng (review Group 5 #1)', () => {
    const blank = reducer(searching, {
      type: 'search',
      attackSpecId: 'a',
      patch: { coarseN: Number.NaN },
    })
    expect(buildBody(blank)).toBeNull()
    expect(canAdvance(blank)).toBe(false)
    expect(hasSearchInputError(searching.attacks, { [searchErrorKey('a')]: true })).toBe(true)
    expect(hasSearchInputError(searching.attacks, { a: true })).toBe(false)
    // Lỗi ô level của attack quét lưới không chặn ước lượng (như Phase 5).
    expect(hasSearchInputError(FULL.attacks, { a: true, [searchErrorKey('a')]: true })).toBe(false)
  })

  it('thêm attack ở Khám phá giữ chế độ và cấu hình tìm ngưỡng của attack đã có (review Group 5 #5)', () => {
    const { config } = listMocks<ExperimentClone>('experiment_clone')[0]
    const first = { ...config.attacks[0], attack_spec_id: 'a', grid: { levels: [2, 4, 8] } }
    const added = reducer(searching, {
      type: 'drafted',
      key: 'k',
      merge: true,
      clone: {
        config: {
          ...config,
          attacks: [first, { ...first, attack_spec_id: 'moi' }],
        },
        warnings: [],
      },
    })
    expect(added.attacks[0]).toMatchObject({ mode: 'search', search: SEARCH })
    expect(added.attacks[1]).toMatchObject({ attackSpecId: 'moi', mode: 'grid', search: null })
  })

  it('nhân bản experiment tìm ngưỡng giữ cấu hình tìm ngưỡng', () => {
    const detail = listMocks<ExperimentDetail>('experiment_detail').find((d) =>
      d.config.attacks.some((a) => a.mode === 'search'),
    )
    if (!detail) throw new Error('Thiếu mock experiment tìm ngưỡng')
    const draft = draftFromClone(detail.config, [], 'dv')
    const body = buildBody(draft)
    expect(body?.attacks.map((a) => [a.mode, a.search ?? null, a.grid?.levels ?? null])).toEqual(
      detail.config.attacks.map((a) => [a.mode, a.search ?? null, a.grid?.levels ?? null]),
    )
  })

  it('chi phí tối đa: "tối đa ~X (tối đa N điểm)"; thiếu số đo thì nói rõ', () => {
    const [estimate] = listMocks<EstimateResponse>('estimate_response').filter(
      (e) => (e.searches ?? []).length === 2,
    )
    const [first] = estimate.searches ?? []
    expect(searchCostSummary(estimate, first.attack_spec_id)).toBe(
      `Tối đa ~${formatDuration(first.max_seconds)} (tối đa ${first.max_points} điểm)`,
    )
    const missing = {
      ...estimate,
      searches: [{ ...first, max_seconds: null }],
    }
    expect(searchCostSummary(missing, first.attack_spec_id)).toContain('Chưa đo được')
    expect(searchCostSummary(estimate, 'khac')).toBeNull()
  })

  it('đếm run quét lưới và điểm tối đa của tìm ngưỡng', () => {
    const estimate = {
      searches: [
        { attack_spec_id: 'a', max_points: 23, max_subset_points: 11, max_full_points: 12 },
      ],
    } as EstimateResponse
    expect(runCounts(WITH_PATCH, undefined)).toEqual({ grid: 2, maxPoints: 0 })
    expect(runCounts(searching, estimate)).toEqual({ grid: 0, maxPoints: 23 })
  })

  it('ước lượng hiển thị: có tìm ngưỡng thì là "tối đa ~X (tối đa N điểm)"', () => {
    const all = listMocks<EstimateResponse>('estimate_response')
    const grid = all.find((e) => (e.searches ?? []).length === 0 && e.total_seconds)
    const mixed = all.find((e) => (e.searches ?? []).length === 2 && e.max_total_seconds)
    const missing = all.find((e) => (e.searches ?? []).length > 0 && e.max_total_seconds === null)
    if (!grid || !mixed || !missing) throw new Error('Thiếu mock ước lượng')
    expect(estimateText(grid)).toBe(formatDuration(grid.total_seconds))
    expect(estimateText(mixed)).toBe(
      `tối đa ~${formatDuration(mixed.max_total_seconds)} (tối đa 34 điểm)`,
    )
    expect(estimateText(missing)).toBe('chưa ước lượng được tối đa (tối đa 34 điểm)')
    expect(estimateText(undefined)).toBe('—')
  })
})
