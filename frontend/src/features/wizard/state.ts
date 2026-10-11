/**
 * Trạng thái nháp của wizard (requirements.md Phase 5, Frontend: wizard): thuần, lưu
 * sessionStorage để giữ qua lần tải lại trang, xóa sau khi tạo thành công. Phase 6 thêm slice huấn
 * luyện cho attack cần train (patch) và công tắc dừng sớm. Phase 7 thêm chế độ tự tìm ngưỡng theo
 * từng attack. Phase 8 thêm attack bắt buộc của protocol (khóa trên giao diện) và kích thước slice
 * tối thiểu. Phase R3 gộp thành 3 bước: mode và preset, model và dữ liệu, rồi attack lấy từ
 * `POST /experiments/draft` (requirements.md Phase R3, Wizard 3 bước).
 */
import type {
  CloneWarning,
  DraftNote,
  EstimateResponse,
  ExperimentCreateInput,
  ExperimentCreateOutput,
  ExperimentDraftRequest,
  ExperimentMode,
  ExperimentPreset,
  FieldError,
} from '@/contracts/api'

import { applyLocks, type RequiredLock, withoutLockedFields, withRequiredLevels } from './protocol'
import { fromSearchConfig, type SearchDraft, toSearchConfig } from './search'

export const STEPS = [
  { step: 1, title: 'Mục đích' },
  { step: 2, title: 'Model và dữ liệu' },
  { step: 3, title: 'Attack và xác nhận' },
] as const

export type Step = (typeof STEPS)[number]['step']
export const LAST_STEP: Step = 3

export type PresetKey = ExperimentPreset['key']
/** Preset chọn sẵn (Phase R3: "chỉ dùng lựa chọn mặc định cộng chọn model/slice"). */
export const DEFAULT_PRESET: PresetKey = 'standard'

/** Seed cố định của mọi attack (requirements.md Phase 5: tái lập được, trúng cache). */
export const SEED = 0
/** Phase R3: khóa `v3` vì số bước đổi (6 → 3); nháp `v2` cũ bị bỏ qua. Nháp `v3` thiếu trường
 * được điền mặc định, không mất trường nào. */
export const STORAGE_KEY = 'advertest.wizard.v3'

export type AttackMode = 'grid' | 'search'

export interface AttackDraft {
  attackSpecId: string
  specSha256: string
  levels: number[]
  /** Spec cần train trên slice huấn luyện trước khi đánh giá (patch, Phase 6). */
  requiresTraining: boolean
  trainingSliceId: string | null
  /** Phase 7: quét lưới hoặc tự tìm ngưỡng (chỉ spec không cần train). */
  mode: AttackMode
  /** Cấu hình tìm ngưỡng; giữ lại khi chuyển về quét lưới để bật lại không mất giá trị. */
  search: SearchDraft | null
}

export interface Draft {
  step: Step
  /** Phase R3: Khám phá dùng protocol `dev`; Chính thức chọn protocol `active`. */
  mode: ExperimentMode
  preset: PresetKey
  protocolId: string | null
  modelId: string | null
  datasetVersionId: string | null
  sliceId: string | null
  mappingId: string | null
  targetId: string | null
  limitSeconds: number | null
  attacks: AttackDraft[]
  /** Dừng sớm khi model đã sụp, áp cho mọi attack (`grid.early_stop`; người dùng chốt ở Group 6). */
  earlyStop: boolean
  /** Cấu hình nhân bản có attack bật và attack tắt dừng sớm (chỉ tạo được qua API). */
  earlyStopMixed: boolean
  name: string
  clonedFrom: string | null
  cloneWarnings: CloneWarning[]
  /** Phase 8: attack bắt buộc của protocol đang chọn (đã áp vào `attacks`, bị khóa). */
  required: RequiredLock[]
  /** Protocol mà `required` được tính cho (null: chưa tải protocol). */
  requiredFor: string | null
  /** `min_slice_size` của protocol (slice nhỏ hơn bị ẩn ở bước 2). */
  minSliceSize: number | null
  /** Phase R3: slice huấn luyện gửi kèm `POST /experiments/draft` (spec cần train). */
  trainingSliceId: string | null
  /** Phase R3: experiment Khám phá nguồn khi nâng lên chính thức. */
  promotedFrom: string | null
  /** Lưu ý của bản nháp từ server (`slice_too_small`). */
  notes: DraftNote[]
  /** Request `draft` đã dựng `attacks` (null: attack chưa lấy từ server). Bước 2 đổi lựa chọn thì
   * khóa đổi và bản nháp được dựng lại. */
  draftKey: string | null
}

export const EMPTY_DRAFT: Draft = {
  step: 1,
  mode: 'exploration',
  preset: DEFAULT_PRESET,
  protocolId: null,
  modelId: null,
  datasetVersionId: null,
  sliceId: null,
  mappingId: null,
  targetId: null,
  limitSeconds: null,
  attacks: [],
  earlyStop: true,
  earlyStopMixed: false,
  name: '',
  clonedFrom: null,
  cloneWarnings: [],
  required: [],
  requiredFor: null,
  minSliceSize: null,
  trainingSliceId: null,
  promotedFrom: null,
  notes: [],
  draftKey: null,
}

export type Action =
  | { type: 'go'; step: Step }
  | { type: 'experimentMode'; mode: ExperimentMode }
  | { type: 'preset'; key: PresetKey }
  | { type: 'protocol'; id: string }
  | { type: 'requirements'; protocolId: string; locks: RequiredLock[]; minSliceSize: number }
  | { type: 'model'; id: string }
  | { type: 'datasetVersion'; id: string }
  | { type: 'slice'; id: string }
  | { type: 'dataSlice'; datasetVersionId: string; sliceId: string }
  | { type: 'draftTrainingSlice'; id: string }
  | { type: 'mapping'; id: string | null }
  | { type: 'target'; id: string; defaultLimitSeconds: number }
  | { type: 'limit'; seconds: number | null }
  | { type: 'toggleAttack'; attackSpecId: string; specSha256: string; requiresTraining: boolean }
  | { type: 'levels'; attackSpecId: string; levels: number[] }
  | { type: 'mode'; attackSpecId: string; mode: AttackMode; defaults: SearchDraft }
  | { type: 'search'; attackSpecId: string; patch: Partial<SearchDraft> }
  | { type: 'trainingSlice'; attackSpecId: string; id: string }
  | { type: 'earlyStop'; on: boolean }
  | { type: 'drafted'; key: string; clone: DraftResult; merge: boolean }
  | { type: 'name'; name: string }
  | { type: 'load'; draft: Draft }

/** Phần của `ExperimentClone` mà wizard dùng (bản nháp từ `draft`, `promote`, `clone`). */
export interface DraftResult {
  config: ExperimentCreateOutput
  warnings: CloneWarning[]
  notes?: DraftNote[]
}

export function reducer(draft: Draft, action: Action): Draft {
  switch (action.type) {
    case 'go':
      return { ...draft, step: action.step }
    case 'experimentMode':
      // Đổi mode: chọn lại protocol (Khám phá tự chọn protocol dev ở WizardPage).
      return draft.mode === action.mode
        ? draft
        : {
            ...draft,
            mode: action.mode,
            protocolId: null,
            required: [],
            requiredFor: null,
            minSliceSize: null,
          }
    case 'preset':
      return { ...draft, preset: action.key }
    case 'protocol':
      // Đổi protocol: bỏ khóa cũ (attack đã thêm vẫn giữ), khóa mới áp khi tải xong protocol.
      return draft.protocolId === action.id
        ? draft
        : { ...draft, protocolId: action.id, required: [], requiredFor: null, minSliceSize: null }
    case 'requirements':
      if (action.protocolId !== draft.protocolId) return draft
      return {
        ...draft,
        required: action.locks,
        requiredFor: action.protocolId,
        minSliceSize: action.minSliceSize,
        attacks: applyLocks(draft.attacks, action.locks),
      }
    case 'model':
      // Mapping phụ thuộc model: chọn lại.
      return draft.modelId === action.id ? draft : { ...draft, modelId: action.id, mappingId: null }
    case 'datasetVersion':
      return draft.datasetVersionId === action.id
        ? draft
        : {
            ...draft,
            datasetVersionId: action.id,
            sliceId: null,
            mappingId: null,
            attacks: withoutTrainingSlices(draft.attacks),
          }
    case 'slice':
      // Slice huấn luyện phải không giao với slice đánh giá: đổi slice thì chọn lại.
      return draft.sliceId === action.id
        ? draft
        : { ...draft, sliceId: action.id, attacks: withoutTrainingSlices(draft.attacks) }
    case 'dataSlice': {
      const version = reducer(draft, { type: 'datasetVersion', id: action.datasetVersionId })
      return reducer(version, { type: 'slice', id: action.sliceId })
    }
    case 'draftTrainingSlice':
      return { ...draft, trainingSliceId: action.id }
    case 'mapping':
      return { ...draft, mappingId: action.id }
    case 'target':
      return draft.targetId === action.id
        ? draft
        : { ...draft, targetId: action.id, limitSeconds: action.defaultLimitSeconds }
    case 'limit':
      return { ...draft, limitSeconds: action.seconds }
    case 'toggleAttack': {
      if (lockOf(draft, action.attackSpecId)) return draft // attack bắt buộc: không bỏ được
      const exists = draft.attacks.some((a) => a.attackSpecId === action.attackSpecId)
      const attacks = exists
        ? draft.attacks.filter((a) => a.attackSpecId !== action.attackSpecId)
        : [
            ...draft.attacks,
            {
              attackSpecId: action.attackSpecId,
              specSha256: action.specSha256,
              levels: [],
              requiresTraining: action.requiresTraining,
              trainingSliceId: null,
              mode: 'grid' as const,
              search: null,
            },
          ]
      return { ...draft, attacks }
    }
    case 'trainingSlice':
      return {
        ...draft,
        attacks: draft.attacks.map((a) =>
          a.attackSpecId === action.attackSpecId ? { ...a, trainingSliceId: action.id } : a,
        ),
      }
    case 'earlyStop':
      return { ...draft, earlyStop: action.on, earlyStopMixed: false }
    case 'drafted': {
      // `merge`: thêm attack ở Khám phá; attack đã có giữ level và chế độ người dùng đã sửa.
      const loaded = attacksFromConfig(action.clone.config)
      const current = new Map(draft.attacks.map((a) => [a.attackSpecId, a]))
      return {
        ...draft,
        step: 3,
        draftKey: action.key,
        attacks: action.merge ? loaded.map((a) => current.get(a.attackSpecId) ?? a) : loaded,
        earlyStop: action.merge ? draft.earlyStop : earlyStopOf(action.clone.config).on,
        earlyStopMixed: action.merge
          ? draft.earlyStopMixed
          : earlyStopOf(action.clone.config).mixed,
        cloneWarnings: action.clone.warnings,
        notes: action.clone.notes ?? [],
      }
    }
    case 'levels': {
      // Level bắt buộc không xóa được (vẫn thêm được level khác).
      const lock = lockOf(draft, action.attackSpecId)
      const levels = lock ? withRequiredLevels(action.levels, lock.levels) : action.levels
      return {
        ...draft,
        attacks: draft.attacks.map((a) =>
          a.attackSpecId === action.attackSpecId ? { ...a, levels } : a,
        ),
      }
    }
    case 'mode':
      if (lockOf(draft, action.attackSpecId)) return draft // chế độ theo protocol
      return {
        ...draft,
        attacks: draft.attacks.map((a) =>
          a.attackSpecId === action.attackSpecId
            ? {
                ...a,
                mode: a.requiresTraining ? 'grid' : action.mode,
                search: a.search ?? action.defaults,
              }
            : a,
        ),
      }
    case 'search': {
      const patch = lockOf(draft, action.attackSpecId)
        ? withoutLockedFields(action.patch)
        : action.patch
      return {
        ...draft,
        attacks: draft.attacks.map((a) =>
          a.attackSpecId === action.attackSpecId && a.search !== null
            ? { ...a, search: { ...a.search, ...patch } }
            : a,
        ),
      }
    }
    case 'name':
      return { ...draft, name: action.name }
    case 'load':
      return action.draft
  }
}

/** Khóa theo protocol của một attack (undefined: attack không bắt buộc). */
export function lockOf(draft: Draft, attackSpecId: string): RequiredLock | undefined {
  return draft.required.find((lock) => lock.attackSpecId === attackSpecId)
}

function withoutTrainingSlices(attacks: AttackDraft[]): AttackDraft[] {
  return attacks.map((a) => (a.trainingSliceId === null ? a : { ...a, trainingSliceId: null }))
}

interface StepOptions {
  /** `max_time_limit_s` của máy đang chọn. */
  maxLimitSeconds?: number
  /** Ô nhập của phần "Tùy chỉnh nâng cao" đang có giá trị sai. */
  levelInputError?: boolean
  /** Bản nháp cần slice huấn luyện (protocol bắt buộc spec cần train). */
  needsTrainingSlice?: boolean
}

/** Bước 2 đủ để dựng `POST /experiments/draft`. */
function dataReady(draft: Draft, options: StepOptions): boolean {
  return (
    draft.modelId !== null &&
    draft.sliceId !== null &&
    draft.mappingId !== null &&
    draft.targetId !== null &&
    draft.limitSeconds !== null &&
    draft.limitSeconds > 0 &&
    (options.maxLimitSeconds === undefined || draft.limitSeconds <= options.maxLimitSeconds) &&
    (!options.needsTrainingSlice || draft.trainingSliceId !== null)
  )
}

/** Bước hiện tại đủ dữ liệu để sang bước sau chưa (bước 3: đủ để tạo experiment). */
export function canAdvance(draft: Draft, options: StepOptions = {}): boolean {
  switch (draft.step) {
    case 1:
      return draft.protocolId !== null
    case 2:
      return dataReady(draft, options)
    case 3:
      return (
        !options.levelInputError && draft.attacks.length > 0 && draft.attacks.every(attackReady)
      )
  }
}

/**
 * Câu nói rõ còn thiếu gì ở bước hiện tại (hiện cạnh nút "Tiếp" khi nút bị khóa), để người dùng
 * không phải đoán. `null` khi đã đủ.
 */
export function missingHint(draft: Draft, options: StepOptions = {}): string | null {
  if (canAdvance(draft, options)) return null
  switch (draft.step) {
    case 1:
      return draft.mode === 'official'
        ? 'Chọn protocol của kiểm thử chính thức.'
        : 'Đang tải protocol dev…'
    case 2:
      if (draft.modelId === null) return 'Chọn model bạn muốn kiểm thử.'
      if (draft.sliceId === null) return 'Chọn dataset và slice ảnh.'
      if (draft.mappingId === null) return 'Chọn class mapping giữa dataset và model.'
      if (draft.targetId === null) return 'Chọn máy sẽ chạy experiment.'
      if (options.needsTrainingSlice && draft.trainingSliceId === null)
        return 'Chọn slice huấn luyện cho attack cần train.'
      if (
        options.maxLimitSeconds !== undefined &&
        draft.limitSeconds !== null &&
        draft.limitSeconds > options.maxLimitSeconds
      )
        return 'Giới hạn thời gian đang vượt mức tối đa của máy này.'
      return 'Đặt giới hạn thời gian lớn hơn 0.'
    case 3: {
      if (options.levelInputError) return 'Sửa ô đang báo lỗi trong "Tùy chỉnh nâng cao".'
      if (draft.attacks.length === 0) return 'Chọn ít nhất một attack.'
      const notReady = draft.attacks.find((a) => !attackReady(a))
      if (notReady?.mode === 'search') return 'Điền đủ các ô của phần tự tìm ngưỡng.'
      if (notReady?.requiresTraining && notReady.trainingSliceId === null)
        return 'Chọn slice huấn luyện cho attack cần train.'
      return 'Giữ ít nhất một level cho mỗi attack.'
    }
  }
}

/** Attack đủ cấu hình: quét lưới có level (và slice huấn luyện khi cần train); tìm ngưỡng có cấu
 * hình với mọi trường là số (luật chi tiết của từng trường báo qua `inputErrors`). */
function attackReady(a: AttackDraft): boolean {
  if (a.mode === 'search') return a.search !== null && searchComplete(a.search)
  return a.levels.length > 0 && (!a.requiresTraining || a.trainingSliceId !== null)
}

/** Ô số đang trống (`NaN`) thì chưa dựng body: tránh gửi `null` lên ước lượng (review Group 5 #1). */
function searchComplete(search: SearchDraft): boolean {
  return [
    search.threshold,
    search.lo,
    search.hi,
    search.tol,
    search.coarseN,
    search.subsetSize,
    search.bootstrapSamples,
  ].every(Number.isFinite)
}

/** Khóa lỗi nhập của form tìm ngưỡng trong `inputErrors` (ô level dùng `attackSpecId`). */
export function searchErrorKey(attackSpecId: string): string {
  return `search:${attackSpecId}`
}

/** Form tìm ngưỡng của một attack đang chọn có lỗi: chưa gọi ước lượng (review Group 5 #1). */
export function hasSearchInputError(
  attacks: AttackDraft[],
  inputErrors: Record<string, boolean>,
): boolean {
  return attacks.some(
    (a) => a.mode === 'search' && inputErrors[searchErrorKey(a.attackSpecId)] === true,
  )
}

/** Ô nhập đang có giá trị sai ở một attack **đang chọn**, theo chế độ hiện tại của attack (attack
 * đã bỏ chọn hoặc chế độ đang ẩn không tính). */
export function hasLevelInputError(
  attacks: AttackDraft[],
  inputErrors: Record<string, boolean>,
): boolean {
  return attacks.some(
    (a) =>
      inputErrors[a.mode === 'search' ? searchErrorKey(a.attackSpecId) : a.attackSpecId] === true,
  )
}

/** Body gửi lên (`ExperimentCreate`); null khi cấu hình chưa đủ để ước lượng hay tạo. */
export function buildBody(draft: Draft): ExperimentCreateInput | null {
  const { protocolId, modelId, sliceId, mappingId, targetId, limitSeconds } = draft
  if (!protocolId || !modelId || !sliceId || !mappingId || !targetId || !limitSeconds) return null
  if (draft.attacks.length === 0 || !draft.attacks.every(attackReady)) return null
  return {
    schema_version: 1,
    protocol_id: protocolId,
    model_version_id: modelId,
    slice_id: sliceId,
    class_mapping_id: mappingId,
    compute_target_id: targetId,
    attacks: draft.attacks.map((a) =>
      a.mode === 'search' && a.search !== null
        ? {
            schema_version: 1,
            attack_spec_id: a.attackSpecId,
            spec_sha256: a.specSha256,
            mode: 'search' as const,
            grid: null,
            search: toSearchConfig(a.search),
            seed: SEED,
          }
        : {
            schema_version: 1,
            attack_spec_id: a.attackSpecId,
            spec_sha256: a.specSha256,
            mode: 'grid' as const,
            // `early_stop` chỉ gửi khi tắt: mặc định bật, body như Phase 5 (cùng config_sha256).
            grid: draft.earlyStop ? { levels: a.levels } : { levels: a.levels, early_stop: false },
            search: null,
            seed: SEED,
            ...(a.requiresTraining ? { training_slice_id: a.trainingSliceId } : {}),
          },
    ),
    limit: { kind: 'time' as const, value: String(limitSeconds) },
    name: draft.name.trim() || null,
    cloned_from: draft.clonedFrom,
    ...(draft.promotedFrom ? { promoted_from: draft.promotedFrom } : {}),
  }
}

/**
 * Body của `POST /experiments/draft` (null khi bước 2 chưa đủ). `attackSpecIds` chỉ gửi với
 * protocol dev (Khám phá); null là toàn bộ catalog `active` trừ spec cần train.
 */
export function draftRequest(
  draft: Draft,
  attackSpecIds: string[] | null = null,
): ExperimentDraftRequest | null {
  const { protocolId, modelId, sliceId, mappingId, targetId, limitSeconds } = draft
  if (!protocolId || !modelId || !sliceId || !mappingId || !targetId || !limitSeconds) return null
  return {
    protocol_id: protocolId,
    preset: draft.preset,
    model_version_id: modelId,
    slice_id: sliceId,
    class_mapping_id: mappingId,
    compute_target_id: targetId,
    limit: { kind: 'time', value: String(limitSeconds) },
    attack_spec_ids: draft.mode === 'exploration' ? attackSpecIds : null,
    training_slice_id: draft.trainingSliceId,
  }
}

/** Khóa so sánh: cùng lựa chọn ở bước 1–2 thì không dựng lại bản nháp. */
export function draftKeyOf(request: ExperimentDraftRequest): string {
  return JSON.stringify({ ...request, attack_spec_ids: null })
}

const STEP_TWO_FIELDS = new Set([
  'model_version_id',
  'slice_id',
  'class_mapping_id',
  'compute_target_id',
  'limit',
  'training_slice_id',
])

/** Bước chứa trường sai (đường dẫn trường của lỗi 422). */
export function stepOfField(path: string): Step {
  const head = path.split('.')[0]
  if (head === 'protocol_id' || head === 'preset') return 1
  if (STEP_TWO_FIELDS.has(head)) return 2
  return 3
}

/** Lỗi theo đường dẫn trường, và bước sớm nhất có lỗi. */
export function groupFieldErrors(fields: FieldError[]): {
  byPath: Record<string, string>
  firstStep: Step | null
} {
  const byPath: Record<string, string> = {}
  let firstStep: Step | null = null
  for (const field of fields) {
    byPath[field.path] = byPath[field.path]
      ? `${byPath[field.path]}; ${field.message}`
      : field.message
    const step = stepOfField(field.path)
    if (firstStep === null || step < firstStep) firstStep = step
  }
  return { byPath, firstStep }
}

/** Attack của wizard từ một cấu hình (bản nháp của server hoặc experiment gốc). */
export function attacksFromConfig(config: ExperimentCreateOutput): AttackDraft[] {
  return config.attacks.map((a) => ({
    attackSpecId: a.attack_spec_id,
    specSha256: a.spec_sha256,
    levels: [...(a.grid?.levels ?? [])],
    requiresTraining: (a.training_slice_id ?? null) !== null,
    trainingSliceId: a.training_slice_id ?? null,
    mode: a.mode,
    search: a.search ? fromSearchConfig(a.search) : null,
  }))
}

/** Công tắc dừng sớm theo cấu hình; chỉ áp cho attack quét lưới (Phase 7). */
function earlyStopOf(config: ExperimentCreateOutput): { on: boolean; mixed: boolean } {
  const stops = config.attacks.filter((a) => a.grid).map((a) => a.grid?.early_stop !== false)
  return { on: stops.every(Boolean), mixed: stops.some(Boolean) && !stops.every(Boolean) }
}

/** Nháp từ cấu hình nhân bản hoặc nâng lên chính thức, mở tại bước 3 (dataset version tra từ
 * slice). `mode` theo protocol của cấu hình. */
export function draftFromClone(
  config: ExperimentCreateOutput,
  warnings: CloneWarning[],
  datasetVersionId: string | null,
  mode: ExperimentMode = 'exploration',
  notes: DraftNote[] = [],
): Draft {
  const earlyStop = earlyStopOf(config)
  const trainingSliceId = config.attacks.find((a) => a.training_slice_id)?.training_slice_id ?? null
  const draft: Draft = {
    ...EMPTY_DRAFT,
    step: 3,
    mode,
    protocolId: config.protocol_id,
    modelId: config.model_version_id,
    datasetVersionId,
    sliceId: config.slice_id,
    mappingId: config.class_mapping_id,
    targetId: config.compute_target_id,
    limitSeconds: Number(config.limit.value),
    attacks: attacksFromConfig(config),
    earlyStop: earlyStop.on,
    earlyStopMixed: earlyStop.mixed,
    name: config.name ?? '',
    clonedFrom: config.cloned_from ?? null,
    promotedFrom: config.promoted_from ?? null,
    cloneWarnings: warnings,
    notes,
    trainingSliceId,
    // Phase 8: khóa theo protocol áp lại khi tải xong protocol (WizardPage).
    required: [],
    requiredFor: null,
    minSliceSize: null,
  }
  // Lùi về bước 1–2 mà không đổi lựa chọn thì giữ attack của cấu hình gốc.
  const request = draftRequest(draft)
  return { ...draft, draftKey: request ? draftKeyOf(request) : null }
}

type Store = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>

function storage(): Store | null {
  try {
    return typeof sessionStorage === 'undefined' ? null : sessionStorage
  } catch {
    return null // trình duyệt chặn sessionStorage: wizard vẫn chạy, chỉ không giữ nháp
  }
}

export function loadDraft(store: Store | null = storage()): Draft {
  try {
    const raw = store?.getItem(STORAGE_KEY)
    if (!raw) return EMPTY_DRAFT
    const saved = JSON.parse(raw) as Partial<Omit<Draft, 'attacks'>> & {
      attacks?: (Partial<AttackDraft> & Pick<AttackDraft, 'attackSpecId' | 'specSha256'>)[]
    }
    return {
      ...EMPTY_DRAFT,
      ...saved,
      // Gộp sâu từng attack để nháp thiếu trường không làm hỏng wizard.
      attacks: (saved.attacks ?? []).map((a) => ({
        levels: [],
        requiresTraining: false,
        trainingSliceId: null,
        mode: 'grid' as const,
        search: null,
        ...a,
      })),
    }
  } catch {
    return EMPTY_DRAFT
  }
}

export function saveDraft(draft: Draft, store: Store | null = storage()): void {
  try {
    store?.setItem(STORAGE_KEY, JSON.stringify(draft))
  } catch {
    // hết chỗ hoặc bị chặn: bỏ qua, nháp chỉ mất khi tải lại trang
  }
}

export function clearDraft(store: Store | null = storage()): void {
  try {
    store?.removeItem(STORAGE_KEY)
  } catch {
    // như trên
  }
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return '—'
  if (seconds < 60) return `${Math.max(1, Math.round(seconds))} giây`
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes} phút`
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  return rest ? `${hours} giờ ${rest} phút` : `${hours} giờ`
}

/**
 * Phần train patch của một attack trong ước lượng (Phase 6, plan task 31): `training_seconds`
 * chỉ có khi patch chưa có; spec thiếu số đo thì nằm trong `missing_profiles`.
 */
export function trainingSummary(estimate: EstimateResponse, attackSpecId: string): string {
  if (estimate.missing_profiles.includes(attackSpecId)) {
    return 'Chưa đo được thời gian train trên máy này: worker sẽ tự đo.'
  }
  const runs = estimate.runs.filter((r) => r.attack_spec_id === attackSpecId)
  const training = runs.filter(
    (r) => r.training_seconds !== null && r.training_seconds !== undefined,
  )
  if (training.length === 0) return 'Patch đã có sẵn: không cần train.'
  const total = training.reduce((sum, r) => sum + (r.training_seconds ?? 0), 0)
  return `Thời gian train: ${formatDuration(total)} (${training.length} patch cần train)`
}

/**
 * Chi phí tối đa của một attack tìm ngưỡng (Phase 7, plan task 26): "tối đa ~X (tối đa N điểm)".
 * Thiếu số đo thì nói rõ.
 */
export function searchCostSummary(estimate: EstimateResponse, attackSpecId: string): string | null {
  const row = estimate.searches?.find((s) => s.attack_spec_id === attackSpecId)
  if (!row) return null
  const points = `tối đa ${row.max_points} điểm`
  if (row.max_seconds === null || row.max_seconds === undefined) {
    return `Chưa đo được tốc độ trên máy này (${points}).`
  }
  return `Tối đa ~${formatDuration(row.max_seconds)} (${points})`
}

/** Số run quét lưới và số điểm tối đa của tìm ngưỡng (hộp xác nhận). */
export function runCounts(
  draft: Draft,
  estimate: EstimateResponse | undefined,
): { grid: number; maxPoints: number } {
  const grid = draft.attacks
    .filter((a) => a.mode === 'grid')
    .reduce((n, a) => n + a.levels.length, 0)
  const maxPoints = (estimate?.searches ?? []).reduce((n, s) => n + s.max_points, 0)
  return { grid, maxPoints }
}

/**
 * Ước lượng hiển thị (bước 3, tóm tắt, thanh dưới): có attack tìm ngưỡng thì là chi phí tối đa
 * "tối đa ~X (tối đa N điểm)" (requirements.md Phase 7, Frontend), không thì như Phase 5.
 */
export function estimateText(estimate: EstimateResponse | undefined): string {
  const searches = estimate?.searches ?? []
  if (!estimate || searches.length === 0) return formatDuration(estimate?.total_seconds)
  const points = searches.reduce((n, s) => n + s.max_points, 0)
  const max = estimate.max_total_seconds
  return max === null || max === undefined
    ? `chưa ước lượng được tối đa (tối đa ${points} điểm)`
    : `tối đa ~${formatDuration(max)} (tối đa ${points} điểm)`
}
