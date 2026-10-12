import { afterEach, describe, expect, it } from 'vitest'

import { listMocks } from '@/api/mocks'
import type {
  AttackSpec,
  AttackSpecView,
  ClassMappingSummary,
  ComputeTargetPublic,
  DatasetSummary,
  EstimateResponse,
  ExperimentPreset,
  ExperimentClone,
  ExperimentDetail,
  ModelSummary,
  ProtocolSummary,
  SliceSummary,
} from '@/contracts/api'
import { render } from '@/test-utils'

import { specTitle } from './levels'
import { defaultSearch, type SearchDraft, targetClassesOf, THRESHOLD_KINDS } from './search'
import { PATCH_SEARCH_LOCKED } from './SearchFields'
import { AttackStep, DataStep, EARLY_STOP_LABEL, PurposeStep } from './steps'
import {
  buildBody,
  type Draft,
  draftFromClone,
  EMPTY_DRAFT,
  estimateText,
  formatDuration,
  searchCostSummary,
  STORAGE_KEY,
} from './state'
import { WizardPage } from './WizardPage'

const protocols = listMocks<ProtocolSummary>('protocol_summary')
const models = listMocks<ModelSummary>('model_summary')
const datasets = listMocks<DatasetSummary>('dataset_summary')
const targets = listMocks<ComputeTargetPublic>('compute_target_public')
const specs = listMocks<AttackSpec>('attack_spec')
const slices = listMocks<SliceSummary>('slice_summary')
const mappings = listMocks<ClassMappingSummary>('class_mapping_summary')
const views = listMocks<AttackSpecView>('attack_spec_view')
// Mock chỉ có preset deep: đủ 3 preset cho bước 1.
const deep = listMocks<ExperimentPreset>('experiment_preset')[0]
const presets: ExperimentPreset[] = [
  { ...deep, key: 'fast', title: 'Nhanh', use_search: false, search: null },
  { ...deep, key: 'standard', title: 'Tiêu chuẩn', use_search: false, search: null },
  deep,
]

const BASE: [readonly unknown[], unknown][] = [
  [['protocols'], protocols],
  [['models'], models],
  [['datasets'], datasets],
  [['compute-targets'], targets],
  [['attack-specs'], specs],
  [['experiment-presets'], presets],
  [['slices', 'all'], slices],
]

function withDraft(draft: Draft) {
  const data = new Map([[STORAGE_KEY, JSON.stringify(draft)]])
  Object.defineProperty(globalThis, 'sessionStorage', {
    configurable: true,
    value: {
      getItem: (k: string) => data.get(k) ?? null,
      setItem: (k: string, v: string) => void data.set(k, v),
      removeItem: (k: string) => void data.delete(k),
    },
  })
}

afterEach(() => {
  Reflect.deleteProperty(globalThis, 'sessionStorage')
})

const noop = () => undefined

/** Văn bản như react-dom/server in ra (thoát `&`, `<`, `>`). */
const escapeHtml = (text: string) =>
  text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')

describe('WizardPage', () => {
  it('bước 1: đúng 3 bước, bước hiện tại aria-current, Mode và Preset, thanh dưới có ước lượng', () => {
    const html = render(<WizardPage />, '/experiments/new', 'engineer', BASE)
    expect(html).toContain('Tạo experiment')
    const steps = [
      ...html.matchAll(/<button[^>]*data-testid="wizard-step"[^>]*>([^<]*)<\/button>/g),
    ]
    expect(steps.map((m) => m[1])).toEqual(['Mục đích', 'Model và dữ liệu', 'Attack và xác nhận'])
    expect(steps[0][0]).toContain('aria-current="step"')
    expect(html).toContain('Bước 1 trên 3')
    expect(html).toContain('role="radiogroup" aria-label="Mode"')
    expect(html).toContain('role="radiogroup" aria-label="Preset"')
    // Mặc định Khám phá và Tiêu chuẩn: chỉ chọn thêm model và slice là đủ.
    // Thẻ đang chọn (có ô icon trước tiêu đề) mang đúng tiêu đề, không lẫn sang thẻ kế tiếp.
    const checked = (title: string) =>
      new RegExp(`aria-checked="true"(?:(?!aria-checked).)*?<span class="font-medium">${title}<`)
    expect(html).toMatch(checked('Khám phá'))
    expect(html).toMatch(checked('Tiêu chuẩn'))
    expect(html).toContain('data-term="exploration"')
    expect(html).toContain('data-testid="uoc-luong-thanh-duoi"')
    expect(html).toContain('env(safe-area-inset-bottom)')
  })

  it('đọc lại nháp từ sessionStorage (tải lại trang giữa wizard)', () => {
    const ready = models.find((m) => m.status === undefined || m.status === 'ready')
    if (!ready) throw new Error('Thiếu mock model sẵn sàng')
    withDraft({ ...EMPTY_DRAFT, step: 2, protocolId: protocols[0].id, modelId: ready.id })
    const html = render(<WizardPage />, '/experiments/new', 'engineer', BASE)
    expect(html).toContain('Bước 2 trên 3')
    expect(html).toMatch(new RegExp(`<option value="${ready.id}" selected=""`))
  })

  it('bước 3: tóm tắt, cảnh báo nhân bản, ước lượng từng run, seed 0, nút Tạo experiment', () => {
    const clone = listMocks<ExperimentClone>('experiment_clone').find((c) => c.warnings.length)
    if (!clone) throw new Error('Thiếu mock clone')
    const draft = draftFromClone(clone.config, clone.warnings, slices[0].dataset_version_id)
    withDraft(draft)
    const estimate = listMocks<EstimateResponse>('estimate_response')[0]
    const html = render(<WizardPage />, '/experiments/new', 'engineer', [
      ...BASE,
      [['estimate', JSON.stringify(buildBody(draft))], estimate],
    ])
    expect(html).toContain('Bước 3 trên 3')
    expect(html).toContain(clone.warnings[0].message)
    expect(html).toContain('Ước lượng từng run')
    expect(html).toContain('Tạo experiment</button>')
    expect(html).not.toContain('Chạy experiment')
    expect(html).toMatch(/Seed<\/dt><dd[^>]*>0</)
  })

  it('bước 3: lưu ý của bản nháp (slice nhỏ hơn protocol yêu cầu)', () => {
    const promoted = listMocks<ExperimentClone>('experiment_clone').find(
      (c) => c.config.promoted_from,
    )
    if (!promoted) throw new Error('Thiếu mock nâng lên chính thức')
    withDraft(draftFromClone(promoted.config, [], null, 'official', promoted.notes ?? []))
    const html = render(<WizardPage />, '/experiments/new', 'engineer', BASE)
    expect(html).toContain('data-testid="draft-notes"')
    expect(html).toContain(escapeHtml(promoted.notes?.[0]?.message ?? ''))
  })

  it('Phase 6 bước 3: bảng ước lượng có cột thời gian train patch', () => {
    const clone = listMocks<ExperimentClone>('experiment_clone')[0]
    const draft = draftFromClone(clone.config, [], slices[0].dataset_version_id)
    withDraft(draft)
    const estimate = listMocks<EstimateResponse>('estimate_response').find((e) =>
      e.runs.some((r) => r.training_seconds),
    )
    if (!estimate) throw new Error('Thiếu mock ước lượng có training_seconds')
    const html = render(<WizardPage />, '/experiments/new', 'engineer', [
      ...BASE,
      [['estimate', JSON.stringify(buildBody(draft))], estimate],
    ])
    expect(html).toContain('Train patch')
    const seconds = estimate.runs.find((r) => r.training_seconds)?.training_seconds ?? null
    expect(html).toContain(`<td class="py-1">${formatDuration(seconds)}</td>`)
  })
})

describe('Phase 7: chi phí tối đa của tìm ngưỡng ở bước 3', () => {
  const detail = listMocks<ExperimentDetail>('experiment_detail').find((d) =>
    d.config.attacks.some((a) => a.mode === 'search'),
  )
  if (!detail) throw new Error('Thiếu mock experiment tìm ngưỡng')
  const draft = { ...draftFromClone(detail.config, [], slices[0].dataset_version_id), name: '' }
  const estimate = listMocks<EstimateResponse>('estimate_response').find(
    (e) => (e.searches ?? []).length === 2 && e.max_exceeds_limit,
  )
  if (!estimate) throw new Error('Thiếu mock ước lượng tìm ngưỡng')
  const cache: [readonly unknown[], unknown][] = [
    ...BASE,
    [['estimate', JSON.stringify(buildBody(draft))], estimate],
  ]

  it('"tối đa" theo từng attack, tổng tối đa, cảnh báo vượt giới hạn', () => {
    withDraft(draft)
    const html = render(<WizardPage />, '/experiments/new', 'engineer', cache)
    expect(html).toContain('Bước 3 trên 3')
    expect(html).toContain('data-testid="chi-phi-tim-nguong"')
    for (const s of estimate.searches ?? []) {
      expect(html).toContain(searchCostSummary(estimate, s.attack_spec_id))
    }
    expect(html).toContain(escapeHtml(estimateText(estimate)))
    expect(html).toContain('Chi phí tối đa của tìm ngưỡng vượt giới hạn thời gian')
  })

  it('validation.md: không có ô số tự do ngoài "Tùy chỉnh nâng cao"', () => {
    withDraft(draft)
    const html = render(<WizardPage />, '/experiments/new', 'engineer', cache)
    expect(html).toContain('type="number"')
    // Bỏ mọi khối <details> (có thể lồng nhau) rồi tìm ô số còn lại.
    let outside = html
    for (;;) {
      const next = outside.replace(/<details(?:(?!<details)[\s\S])*?<\/details>/, '')
      if (next === outside) break
      outside = next
    }
    expect(outside).not.toContain('type="number"')
    expect(html).toMatch(/<details[^>]*>\s*<summary[^>]*>Tùy chỉnh nâng cao</)
  })
})

describe('bước 1', () => {
  it('Chính thức: ô chọn Protocol chỉ có protocol active, kèm chi tiết protocol', () => {
    const html = render(
      <PurposeStep draft={{ ...EMPTY_DRAFT, mode: 'official' }} dispatch={noop} errors={{}} />,
      '/',
      'engineer',
      BASE,
    )
    expect(html).toContain('<label for="wizard-protocol"')
    const options = [...html.matchAll(/<option value="([^"]+)"/g)].map((m) => m[1])
    const active = protocols.filter((p) => p.status === 'active').map((p) => p.id)
    expect(options).toEqual(active)
  })

  it('Khám phá: không có ô chọn protocol (dùng protocol dev)', () => {
    const html = render(
      <PurposeStep draft={EMPTY_DRAFT} dispatch={noop} errors={{}} />,
      '/',
      'engineer',
      BASE,
    )
    expect(html).not.toContain('wizard-protocol')
    for (const preset of presets) expect(html).toContain(preset.title)
  })
})

describe('bước 2', () => {
  const draft: Draft = {
    ...EMPTY_DRAFT,
    step: 2,
    modelId: models[0].id,
    datasetVersionId: slices[0].dataset_version_id,
    sliceId: slices[0].id,
  }
  const render2 = (d: Draft, extra: [readonly unknown[], unknown][] = [], training = false) =>
    render(
      <DataStep draft={d} dispatch={noop} errors={{}} needsTrainingSlice={training} />,
      '/',
      'engineer',
      [...BASE, ...extra],
    )

  it('ô chọn Model (chỉ model sẵn sàng), Dataset và slice, Máy chạy; không có ô số', () => {
    const html = render2(draft, [[['class-mappings', draft.datasetVersionId, draft.modelId], []]])
    for (const id of ['wizard-model', 'wizard-slice', 'wizard-target']) {
      expect(html).toContain(`<label for="${id}"`)
    }
    const select = html.slice(html.indexOf('id="wizard-model"'), html.indexOf('</select>'))
    const options = [...select.matchAll(/<option value="([^"]+)"/g)].map((m) => m[1])
    const usable = models.filter((m) => m.status !== 'checking' && m.status !== 'check_failed')
    expect(options).toEqual(usable.map((m) => m.id))
    expect(usable.length).toBeLessThan(models.length)
    expect(html).toContain(`${slices[0].name} (${slices[0].size} ảnh)`)
    expect(html).not.toContain('type="number"')
  })

  it('không có class mapping thì báo rõ', () => {
    const html = render2(draft, [[['class-mappings', draft.datasetVersionId, draft.modelId], []]])
    expect(html).toContain('Chưa có class mapping')
    expect(html).toContain('role="alert"')
  })

  it('một mapping thì tự chọn', () => {
    const html = render2(draft, [
      [['class-mappings', draft.datasetVersionId, draft.modelId], mappings.slice(0, 1)],
    ])
    expect(html).toContain('Tự chọn class mapping duy nhất')
  })

  it('protocol yêu cầu slice lớn hơn thì ẩn slice nhỏ', () => {
    const html = render2({ ...draft, minSliceSize: 1_000_000 })
    expect(html).toContain('data-testid="slice-an"')
  })

  it('giới hạn thời gian là thanh trượt có giá trị gợi ý; máy local ghi miễn phí', () => {
    const target = targets[0]
    const html = render2({ ...draft, targetId: target.id, limitSeconds: 3600 })
    const max = Math.floor(target.max_time_limit_s / 60)
    expect(html).toMatch(new RegExp(`id="wizard-limit" type="range" min="5" max="${max}"`))
    expect(html).toContain(`Gợi ý ${Math.round(target.default_time_limit_s / 60)} phút`)
    expect(html).toContain('60 phút')
    expect(html).toContain('miễn phí')
  })

  it('Phase 6: slice huấn luyện chỉ liệt kê slice không giao, cùng version, ≤ max ảnh', () => {
    const patch = specs.find((s) => s.requires_training)
    if (!patch?.training) throw new Error('Thiếu mock adv_patch')
    const dv = draft.datasetVersionId ?? ''
    const candidate = (name: string, size: number, version = dv): SliceSummary => ({
      ...slices[0],
      id: `00000000-0000-4000-8000-${String(size).padStart(12, '0')}`,
      name,
      size,
      dataset_version_id: version,
    })
    const html = render2(
      draft,
      [
        [
          ['slices', 'disjoint-from', slices[0].id],
          [
            candidate('train-ok', patch.training.max_training_images),
            candidate('train-qua-lon', patch.training.max_training_images + 1),
            candidate('train-khac-version', 10, 'khac'),
          ],
        ],
      ],
      true,
    )
    expect(html).toContain('<label for="wizard-training-slice"')
    expect(html).toContain('train-ok')
    expect(html).not.toContain('train-qua-lon')
    expect(html).not.toContain('train-khac-version')
    expect(render2(draft, [[['slices', 'disjoint-from', slices[0].id], []]], true)).toContain(
      'Chưa có slice huấn luyện nào không giao',
    )
  })
})

describe('bước 3', () => {
  const draft: Draft = {
    ...EMPTY_DRAFT,
    step: 3,
    modelId: models[0].id,
    datasetVersionId: slices[0].dataset_version_id,
  }
  const grid = (spec: AttackSpec, levels: number[]) => ({
    attackSpecId: spec.id,
    specSha256: spec.spec_sha256,
    levels,
    requiresTraining: spec.requires_training === true,
    trainingSliceId: null,
    mode: 'grid' as const,
    search: null,
  })
  const render3 = (
    d: Draft,
    errors: Record<string, string> = {},
    estimate?: EstimateResponse,
    catalog: AttackSpec[] = specs,
    extra: [readonly unknown[], unknown][] = [],
  ) =>
    render(
      <AttackStep
        draft={d}
        dispatch={noop}
        errors={errors}
        model={models.find((m) => m.id === d.modelId)}
        onInputError={noop}
        onAdd={noop}
        adding={false}
        estimate={estimate}
      />,
      '/',
      'engineer',
      [...BASE, [['attack-specs'], catalog], ...extra],
    )

  it('công tắc chế độ trong phần nâng cao; cảnh báo model không hỗ trợ gradient; lỗi server tại attack', () => {
    const noGrad = models.find((m) => !m.supports_gradients)
    if (!noGrad) throw new Error('Thiếu mock model không gradient')
    const spec = specs.find((s) => s.requires_gradients) ?? specs[0]
    const html = render3(
      { ...draft, modelId: noGrad.id, attacks: [grid(spec, [4])] },
      { 'attacks.0.grid.levels': 'Level 40 nằm ngoài dải' },
    )
    expect(html).toContain(`data-testid="attack-row" data-attack="${spec.name}"`)
    expect(html).toContain(`aria-label="Chế độ của ${spec.name}"`)
    expect(html).toMatch(/aria-checked="true"[^>]*>Quét lưới</)
    expect(html).toMatch(/aria-checked="false"[^>]*>Tự tìm ngưỡng</)
    expect(html).toContain('các run sẽ bị bỏ qua')
    expect(html).toContain('Level 40 nằm ngoài dải')
    expect(html).toContain(`aria-label="Bỏ attack ${spec.name}"`)
  })

  it('chip level có nhãn và data-level; metadata cho tên dễ đọc và mức sát thực tế', () => {
    const snow = views.find((v) => v.metadata?.level_labels?.['2'])
    if (!snow?.metadata) throw new Error('Thiếu mock attack_spec_view có nhãn level')
    const html = render3({ ...draft, attacks: [grid(snow, [2])] }, {}, undefined, [snow])
    expect(html).toContain(snow.metadata.display_name)
    expect(html).toContain(snow.metadata.description)
    expect(html).toMatch(/data-level="2" aria-pressed="true"[^>]*>vừa<span[^>]*>2</)
    expect(html).toMatch(/data-level="1" aria-pressed="false"[^>]*>lất phất/)
    expect(html).toContain('data-term="level"')
  })

  it('ô gõ thêm level chỉ nằm trong "Tùy chỉnh nâng cao", chỉ cho tham số liên tục', () => {
    const continuous = specs.find(
      (s) => s.primary_param.type === 'continuous' && !s.requires_training,
    )
    const discrete = specs.find((s) => s.primary_param.type === 'discrete')
    if (!continuous || !discrete) throw new Error('thiếu mock')
    const html = render3({ ...draft, attacks: [grid(continuous, [4])] })
    expect(html).toMatch(/<details[^>]*>(?:(?!<\/details>).)*Thêm level khác/)
    expect(html.split('<details')[0]).not.toContain('Thêm level khác')
    expect(render3({ ...draft, attacks: [grid(discrete, [1])] })).not.toContain('Thêm level khác')
  })

  it('Phase 6: chip severity bật/tắt, công tắc dừng sớm bật trong phần nâng cao', () => {
    const fog = specs.find((s) => s.name === 'fog')
    if (!fog) throw new Error('Thiếu mock fog')
    const html = render3({ ...draft, attacks: [grid(fog, [1, 3])] })
    expect(html).toMatch(/<input type="checkbox" role="switch"[^>]*checked=""/)
    expect(html).toContain(EARLY_STOP_LABEL)
    const pressed = [...html.matchAll(/aria-pressed="(true|false)"[^>]*>(\d)</g)].map((m) => [
      m[2],
      m[1],
    ])
    expect(pressed).toEqual([
      ['1', 'true'],
      ['2', 'false'],
      ['3', 'true'],
      ['4', 'false'],
      ['5', 'false'],
    ])
  })

  it('Khám phá thêm attack bằng thẻ có icon và mô tả; Chính thức thì không', () => {
    const [first, ...rest] = specs
    const exploration = render3({ ...draft, attacks: [grid(first, [4])] })
    expect(exploration).toContain('Thêm attack')
    for (const spec of rest) expect(exploration).toContain(`aria-label="Thêm ${specTitle(spec)}"`)
    expect(exploration).toContain('Mô phỏng: </span>')
    expect(exploration).toContain('Tấn công')
    const official = render3({ ...draft, mode: 'official', attacks: [grid(first, [4])] })
    expect(official).not.toContain('Thêm attack')
  })

  describe('Phase 7: tự tìm ngưỡng', () => {
    const pgd = specs.find((s) => s.name === 'pgd_linf')
    const fog = specs.find((s) => s.name === 'fog')
    const patch = specs.find((s) => s.requires_training)
    if (!pgd || !fog || !patch) throw new Error('Thiếu mock pgd_linf, fog hoặc adv_patch')
    const slice = slices.find((s) => s.size === 300) ?? slices[0]
    const mapping = mappings[0]
    const searchDraft = (spec: AttackSpec, patchSearch: Partial<SearchDraft> = {}): Draft => ({
      ...draft,
      sliceId: slice.id,
      mappingId: mapping.id,
      attacks: [
        {
          attackSpecId: spec.id,
          specSha256: spec.spec_sha256,
          levels: [],
          requiresTraining: false,
          trainingSliceId: null,
          mode: 'search',
          search: { ...defaultSearch(spec.primary_param, slice.size), ...patchSearch },
        },
      ],
    })
    const renderSearch = (
      d: Draft,
      errors: Record<string, string> = {},
      estimate?: EstimateResponse,
    ) =>
      render3(d, errors, estimate, specs, [
        [['slices', slice.dataset_version_id], [slice]],
        [['class-mappings', d.datasetVersionId, d.modelId], [mapping]],
      ])

    it('form: 3 loại ngưỡng có giải thích, ngưỡng %, class đích, tol mặc định (hi − lo)/256, Nâng cao thu gọn', () => {
      const html = renderSearch(searchDraft(pgd))
      for (const kind of THRESHOLD_KINDS) {
        expect(html).toContain(kind.label)
        expect(html).toContain(kind.hint)
      }
      expect(html).toMatch(/aria-checked="true"[^>]*>Tự tìm ngưỡng</)
      expect(html).toContain('Ngưỡng (%)')
      expect(html).toMatch(/type="range"[^>]*value="20"/)
      for (const name of targetClassesOf(mapping.classes)) {
        expect(html).toContain(`<option value="${name}">`)
      }
      const tol = (pgd.primary_param.max - pgd.primary_param.min) / 256
      expect(html).toContain(`id="tim-nguong-${pgd.id}-tol"`)
      expect(html).toMatch(new RegExp(`id="tim-nguong-${pgd.id}-tol"[^>]*value="${tol}"`))
      // `<details>` không có `open`: phần Nâng cao thu gọn.
      expect(html).toMatch(/<details class="[^"]*">\s*<summary[^>]*>Nâng cao</)
      expect(html).toContain('Số điểm quét thô')
      expect(html).toContain('Số mẫu bootstrap')
      expect(html).not.toContain('data-level=')
      expect(html).not.toContain('data-testid="tap-con-nho"')
    })

    it('tham số rời rạc: lo/hi chọn trong giá trị của spec, không có ô độ chính xác', () => {
      const html = renderSearch(searchDraft(fog))
      expect(html).toContain(`<select id="tim-nguong-${fog.id}-lo"`)
      expect(html).not.toContain(`id="tim-nguong-${fog.id}-tol"`)
    })

    it('cảnh báo tập con dưới 20 ảnh; lỗi zod và lỗi 422 hiện tại trường', () => {
      const small = renderSearch(searchDraft(pgd, { subsetSize: 10 }))
      expect(small).toContain('data-testid="tap-con-nho"')
      const bad = renderSearch(searchDraft(pgd, { coarseN: 9, subsetSize: slice.size + 1 }))
      expect(bad).toContain('Số điểm quét thô từ 3 đến 8')
      expect(bad).toContain(`Tập con tối đa bằng số ảnh của slice (${slice.size})`)
      const server = renderSearch(searchDraft(pgd), {
        'attacks.0.search.threshold': 'Ngưỡng lớn hơn mAP ảnh sạch',
      })
      expect(server).toContain('Ngưỡng lớn hơn mAP ảnh sạch')
    })

    it('hai attack tìm ngưỡng: tên truy cập không trùng (review Group 5 #2)', () => {
      const two = searchDraft(pgd)
      const fogAttack = searchDraft(fog).attacks[0]
      const html = renderSearch({ ...two, attacks: [...two.attacks, fogAttack] })
      const labels = [...html.matchAll(/aria-label="([^"]+)"/g)].map((m) => m[1])
      expect(labels).toContain(`Loại ngưỡng của ${pgd.name}`)
      expect(labels).toContain(`Loại ngưỡng của ${fog.name}`)
      expect(labels).toContain(`Ngưỡng của ${fog.name} (thanh trượt)`)
      expect(new Set(labels).size).toBe(labels.length)
    })

    it('adv_patch: công tắc tìm ngưỡng bị khóa và có giải thích', () => {
      const html = renderSearch({ ...draft, attacks: [grid(patch, [0.1])] })
      expect(html).toMatch(/aria-checked="false" disabled=""[^>]*>Tự tìm ngưỡng</)
      expect(html).toContain(PATCH_SEARCH_LOCKED)
    })

    it('chi phí tối đa của attack tìm ngưỡng từ ước lượng', () => {
      const estimate = listMocks<EstimateResponse>('estimate_response').find((e) =>
        e.searches?.some((s) => s.attack_spec_id === pgd.id),
      )
      if (!estimate) throw new Error('Thiếu mock ước lượng tìm ngưỡng')
      const html = renderSearch(searchDraft(pgd), {}, estimate)
      expect(html).toContain(`data-testid="chi-phi-toi-da-${pgd.id}"`)
      expect(html).toContain(searchCostSummary(estimate, pgd.id))
    })
  })
})
