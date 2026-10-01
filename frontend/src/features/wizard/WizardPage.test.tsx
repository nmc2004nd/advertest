import { afterEach, describe, expect, it } from 'vitest'

import { listMocks } from '@/api/mocks'
import type {
  AttackSpec,
  ClassMappingSummary,
  ComputeTargetPublic,
  DatasetSummary,
  EstimateResponse,
  ExperimentClone,
  ModelSummary,
  ProtocolSummary,
  SliceSummary,
} from '@/contracts/api'
import { render } from '@/test-utils'

import { defaultSearch, type SearchDraft, targetClassesOf, THRESHOLD_KINDS } from './search'
import { PATCH_SEARCH_LOCKED } from './SearchFields'
import { AttackStep, DatasetStep, EARLY_STOP_LABEL, TargetStep } from './steps'
import {
  buildBody,
  type Draft,
  draftFromClone,
  EMPTY_DRAFT,
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

const BASE: [readonly unknown[], unknown][] = [
  [['protocols'], protocols],
  [['models'], models],
  [['datasets'], datasets],
  [['compute-targets'], targets],
  [['attack-specs'], specs],
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

describe('WizardPage', () => {
  it('bước 1: protocol dev có nhãn, thanh bước, thanh dưới có ước lượng', () => {
    const html = render(<WizardPage />, '/experiments/new', 'engineer', BASE)
    expect(html).toContain('Tạo experiment')
    expect(html).toContain('Bước 1/6')
    expect(html).toContain('Dev – không gửi duyệt được')
    expect(html).toContain('data-testid="uoc-luong-thanh-duoi"')
    expect(html).toContain('env(safe-area-inset-bottom)')
  })

  it('đọc lại nháp từ sessionStorage (tải lại trang giữa wizard)', () => {
    withDraft({ ...EMPTY_DRAFT, step: 2, protocolId: protocols[0].id, modelId: models[0].id })
    const html = render(<WizardPage />, '/experiments/new', 'engineer', BASE)
    expect(html).toContain('Bước 2/6')
    expect(html).toContain('aria-checked="true"')
  })

  it('bước 6: tóm tắt, cảnh báo nhân bản, ước lượng từng run, seed 0', () => {
    const clone = listMocks<ExperimentClone>('experiment_clone').find((c) => c.warnings.length)
    if (!clone) throw new Error('Thiếu mock clone')
    const draft = draftFromClone(clone.config, clone.warnings, slices[0].dataset_version_id)
    withDraft(draft)
    const estimate = listMocks<EstimateResponse>('estimate_response')[0]
    const html = render(<WizardPage />, '/experiments/new', 'engineer', [
      ...BASE,
      [['estimate', JSON.stringify(buildBody(draft))], estimate],
    ])
    expect(html).toContain('Bước 6/6')
    expect(html).toContain(clone.warnings[0].message)
    expect(html).toContain('Ước lượng từng run')
    expect(html).toContain('Chạy experiment')
    expect(html).toMatch(/Seed<\/dt><dd[^>]*>0</)
  })

  it('Phase 6 bước 6: bảng ước lượng có cột thời gian train patch', () => {
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

describe('các bước', () => {
  const draft: Draft = {
    ...EMPTY_DRAFT,
    step: 3,
    modelId: models[0].id,
    datasetVersionId: slices[0].dataset_version_id,
  }

  it('bước 3: không có class mapping thì báo rõ', () => {
    const html = render(
      <DatasetStep draft={draft} dispatch={noop} errors={{}} />,
      '/',
      'engineer',
      [
        ...BASE,
        [['slices', draft.datasetVersionId], slices],
        [['class-mappings', draft.datasetVersionId, draft.modelId], []],
      ],
    )
    expect(html).toContain('Chưa có class mapping')
    expect(html).toContain('role="alert"')
  })

  it('bước 3: một mapping thì tự chọn', () => {
    const html = render(
      <DatasetStep draft={draft} dispatch={noop} errors={{}} />,
      '/',
      'engineer',
      [
        ...BASE,
        [['slices', draft.datasetVersionId], slices],
        [['class-mappings', draft.datasetVersionId, draft.modelId], mappings.slice(0, 1)],
      ],
    )
    expect(html).toContain('Tự chọn mapping duy nhất')
  })

  it('bước 4: công tắc chế độ theo attack; cảnh báo model không hỗ trợ gradient; lỗi server tại attack', () => {
    const noGrad = models.find((m) => !m.supports_gradients)
    const spec = specs[0]
    const attackDraft: Draft = {
      ...draft,
      step: 4,
      attacks: [
        {
          attackSpecId: spec.id,
          specSha256: spec.spec_sha256,
          levels: [4],
          requiresTraining: false,
          trainingSliceId: null,
          mode: 'grid',
          search: null,
        },
      ],
    }
    const html = render(
      <AttackStep
        draft={attackDraft}
        dispatch={noop}
        errors={{ 'attacks.0.grid.levels': 'Level 40 nằm ngoài dải' }}
        model={noGrad}
        onLevelInputError={noop}
      />,
      '/',
      'engineer',
      BASE,
    )
    // Phase 7: không còn "Sắp có"; mỗi attack có công tắc riêng, mặc định quét lưới.
    expect(html).not.toContain('Sắp có')
    expect(html).toContain(`aria-label="Chế độ của ${spec.name}"`)
    expect(html).toMatch(/aria-checked="true"[^>]*>Quét lưới</)
    expect(html).toMatch(/aria-checked="false"[^>]*>Tự tìm ngưỡng</)
    expect(html).toContain('các run sẽ bị bỏ qua')
    expect(html).toContain('Level 40 nằm ngoài dải')
    expect(html).toContain('Dùng bộ gợi ý')
  })

  it('Phase 6 bước 4: ba nhóm, công tắc dừng sớm bật, preset toàn catalog, chip severity', () => {
    const fog = specs.find((s) => s.name === 'fog')
    if (!fog) throw new Error('Thiếu mock fog')
    const html = render(
      <AttackStep
        draft={{
          ...draft,
          step: 4,
          attacks: [
            {
              attackSpecId: fog.id,
              specSha256: fog.spec_sha256,
              levels: [1, 3],
              requiresTraining: false,
              trainingSliceId: null,
              mode: 'grid',
              search: null,
            },
          ],
        }}
        dispatch={noop}
        errors={{}}
        model={models[0]}
        onLevelInputError={noop}
      />,
      '/',
      'engineer',
      BASE,
    )
    const headings = [...html.matchAll(/<h3[^>]*>([^<]+)<\/h3>/g)].map((m) => m[1])
    expect(headings).toEqual(['Tấn công', 'Biến đổi điều kiện', 'Che khuất'])
    expect(html).toMatch(/<input type="checkbox" role="switch"[^>]*checked=""/)
    expect(html).toContain(EARLY_STOP_LABEL)
    expect(html).toContain('Toàn bộ catalog')
    // Severity: 5 chip bật/tắt, đang chọn 1 và 3; không có ô nhập tự do.
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
    expect(html).not.toContain('Thêm level (severity')
  })

  it('Phase 6 bước 4: patch chỉ liệt kê slice huấn luyện không giao, cùng version, ≤ 50 ảnh', () => {
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
    const patchDraft: Draft = {
      ...draft,
      step: 4,
      sliceId: slices[0].id,
      attacks: [
        {
          attackSpecId: patch.id,
          specSha256: patch.spec_sha256,
          levels: [0.1, 0.25],
          requiresTraining: true,
          trainingSliceId: null,
          mode: 'grid',
          search: null,
        },
      ],
    }
    const render4 = (training: SliceSummary[]) =>
      render(
        <AttackStep
          draft={patchDraft}
          dispatch={noop}
          errors={{ 'attacks.0.training_slice_id': 'Slice huấn luyện giao với slice đánh giá' }}
          model={models[0]}
          onLevelInputError={noop}
        />,
        '/',
        'engineer',
        [...BASE, [['slices', 'disjoint-from', slices[0].id], training]],
      )
    const html = render4([
      candidate('train-ok', patch.training.max_training_images),
      candidate('train-qua-lon', patch.training.max_training_images + 1),
      candidate('train-khac-version', 10, 'khac'),
    ])
    expect(html).toContain('Slice huấn luyện (bắt buộc)')
    expect(html).toContain('train-ok')
    expect(html).not.toContain('train-qua-lon')
    expect(html).not.toContain('train-khac-version')
    expect(html).toContain('Slice huấn luyện giao với slice đánh giá')
    expect(html).toContain('Dùng bộ gợi ý: 0.1, 0.25')
    expect(render4([])).toContain('Chưa có slice huấn luyện nào không giao')
  })

  describe('Phase 7 bước 4: tự tìm ngưỡng', () => {
    const pgd = specs.find((s) => s.name === 'pgd_linf')
    const fog = specs.find((s) => s.name === 'fog')
    const patch = specs.find((s) => s.requires_training)
    if (!pgd || !fog || !patch) throw new Error('Thiếu mock pgd_linf, fog hoặc adv_patch')
    const slice = slices.find((s) => s.size === 300) ?? slices[0]
    const mapping = mappings[0]
    const searchDraft = (spec: AttackSpec, patchSearch: Partial<SearchDraft> = {}): Draft => ({
      ...draft,
      step: 4,
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
    const render4 = (d: Draft, errors: Record<string, string> = {}, estimate?: EstimateResponse) =>
      render(
        <AttackStep
          draft={d}
          dispatch={noop}
          errors={errors}
          model={models[0]}
          onLevelInputError={noop}
          estimate={estimate}
        />,
        '/',
        'engineer',
        [
          ...BASE,
          [['slices', slice.dataset_version_id], [slice]],
          [['class-mappings', d.datasetVersionId, d.modelId], [mapping]],
        ],
      )

    it('form: 3 loại ngưỡng có giải thích, ngưỡng %, class đích, tol mặc định (hi − lo)/256, Nâng cao thu gọn', () => {
      const html = render4(searchDraft(pgd))
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
      expect(html).not.toContain('Dùng bộ gợi ý')
      expect(html).not.toContain('data-testid="tap-con-nho"')
    })

    it('tham số rời rạc: lo/hi chọn trong giá trị của spec, không có ô độ chính xác', () => {
      const html = render4(searchDraft(fog))
      expect(html).toContain(`<select id="tim-nguong-${fog.id}-lo"`)
      expect(html).not.toContain(`id="tim-nguong-${fog.id}-tol"`)
    })

    it('cảnh báo tập con dưới 20 ảnh; lỗi zod và lỗi 422 hiện tại trường', () => {
      const small = render4(searchDraft(pgd, { subsetSize: 10 }))
      expect(small).toContain('data-testid="tap-con-nho"')
      const bad = render4(searchDraft(pgd, { coarseN: 9, subsetSize: slice.size + 1 }))
      expect(bad).toContain('Số điểm quét thô từ 3 đến 8')
      expect(bad).toContain(`Tập con tối đa bằng số ảnh của slice (${slice.size})`)
      const server = render4(searchDraft(pgd), {
        'attacks.0.search.threshold': 'Ngưỡng lớn hơn mAP ảnh sạch',
      })
      expect(server).toContain('Ngưỡng lớn hơn mAP ảnh sạch')
    })

    it('adv_patch: công tắc tìm ngưỡng bị khóa và có giải thích', () => {
      const html = render4({
        ...draft,
        step: 4,
        attacks: [
          {
            attackSpecId: patch.id,
            specSha256: patch.spec_sha256,
            levels: [0.1],
            requiresTraining: true,
            trainingSliceId: null,
            mode: 'grid',
            search: null,
          },
        ],
      })
      expect(html).toMatch(/aria-checked="false" disabled=""[^>]*>Tự tìm ngưỡng</)
      expect(html).toContain(PATCH_SEARCH_LOCKED)
    })

    it('chi phí tối đa của attack tìm ngưỡng từ ước lượng', () => {
      const estimate = listMocks<EstimateResponse>('estimate_response').find((e) =>
        e.searches?.some((s) => s.attack_spec_id === pgd.id),
      )
      if (!estimate) throw new Error('Thiếu mock ước lượng tìm ngưỡng')
      const html = render4(searchDraft(pgd), {}, estimate)
      expect(html).toContain(`data-testid="chi-phi-toi-da-${pgd.id}"`)
      expect(html).toContain(searchCostSummary(estimate, pgd.id))
    })
  })

  it('bước 5: nhãn máy local, giới hạn vượt tối đa bị báo', () => {
    const target = targets[0]
    const html = render(
      <TargetStep
        draft={{
          ...draft,
          step: 5,
          targetId: target.id,
          limitSeconds: target.max_time_limit_s + 60,
        }}
        dispatch={noop}
        errors={{}}
        estimate={undefined}
      />,
      '/',
      'engineer',
      BASE,
    )
    expect(html).toContain('Miễn phí – máy local')
    expect(html).toContain('Vượt giới hạn tối đa')
    expect(html).toContain('id="gioi-han-phut"')
  })
})
