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

import { AttackStep, DatasetStep, TargetStep } from './steps'
import { buildBody, type Draft, draftFromClone, EMPTY_DRAFT, STORAGE_KEY } from './state'
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

  it('bước 4: "Tự tìm ngưỡng" Sắp có; cảnh báo model không hỗ trợ gradient; lỗi server tại attack', () => {
    const noGrad = models.find((m) => !m.supports_gradients)
    const spec = specs[0]
    const attackDraft: Draft = {
      ...draft,
      step: 4,
      attacks: [{ attackSpecId: spec.id, specSha256: spec.spec_sha256, levels: [4] }],
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
    expect(html).toContain('Sắp có')
    expect(html).toContain('các run sẽ bị bỏ qua')
    expect(html).toContain('Level 40 nằm ngoài dải')
    expect(html).toContain('Dùng bộ gợi ý')
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
