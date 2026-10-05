/**
 * Trạng thái nháp của wizard (requirements.md Phase 5, Frontend: wizard): thuần, lưu
 * sessionStorage để giữ qua lần tải lại trang, xóa sau khi tạo thành công. Phase 6 thêm slice huấn
 * luyện cho attack cần train (patch) và công tắc dừng sớm. Phase 7 thêm chế độ tự tìm ngưỡng theo
 * từng attack; nháp cũ (khóa `v2`) thiếu chế độ thì coi là quét lưới. Phase 8 thêm attack bắt
 * buộc của protocol (khóa trên giao diện) và kích thước slice tối thiểu.
 */
import type {
  CloneWarning,
  EstimateResponse,
  ExperimentCreateInput,
  ExperimentCreateOutput,
  FieldError,
} from '@/contracts/api'

import { applyLocks, type RequiredLock, withoutLockedFields, withRequiredLevels } from './protocol'
import { fromSearchConfig, type SearchDraft, toSearchConfig } from './search'

export const STEPS = [
  { step: 1, title: 'Protocol' },
  { step: 2, title: 'Model' },
  { step: 3, title: 'Dataset và slice' },
  { step: 4, title: 'Attack' },
  { step: 5, title: 'Máy chạy và giới hạn' },
  { step: 6, title: 'Xác nhận' },
] as const

export type Step = (typeof STEPS)[number]['step']

/** Seed cố định của mọi attack (requirements.md Phase 5: tái lập được, trúng cache). */
export const SEED = 0
/** Phase 6: khóa `v2` vì nháp có thêm trường; nháp `v1` cũ bị bỏ qua (requirements.md Phase 6).
 * Phase 7 giữ `v2`: nháp thiếu `mode`/`search` được điền mặc định (quét lưới), không mất trường nào. */
export const STORAGE_KEY = 'advertest.wizard.v2'

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
  /** `min_slice_size` của protocol (slice nhỏ hơn bị ẩn ở bước 3). */
  minSliceSize: number | null
}

export const EMPTY_DRAFT: Draft = {
  step: 1,
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
}

export type Action =
  | { type: 'go'; step: Step }
  | { type: 'protocol'; id: string }
  | { type: 'requirements'; protocolId: string; locks: RequiredLock[]; minSliceSize: number }
  | { type: 'model'; id: string }
  | { type: 'datasetVersion'; id: string }
  | { type: 'slice'; id: string }
  | { type: 'mapping'; id: string | null }
  | { type: 'target'; id: string; defaultLimitSeconds: number }
  | { type: 'limit'; seconds: number | null }
  | { type: 'toggleAttack'; attackSpecId: string; specSha256: string; requiresTraining: boolean }
  | { type: 'levels'; attackSpecId: string; levels: number[] }
  | { type: 'mode'; attackSpecId: string; mode: AttackMode; defaults: SearchDraft }
  | { type: 'search'; attackSpecId: string; patch: Partial<SearchDraft> }
  | { type: 'trainingSlice'; attackSpecId: string; id: string }
  | { type: 'earlyStop'; on: boolean }
  | { type: 'preset'; attacks: AttackDraft[] }
  | { type: 'name'; name: string }
  | { type: 'load'; draft: Draft }

export function reducer(draft: Draft, action: Action): Draft {
  switch (action.type) {
    case 'go':
      return { ...draft, step: action.step }
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
    case 'preset': {
      // Giữ slice huấn luyện, chế độ và cấu hình tìm ngưỡng của attack đã có (review Group 5 #5).
      const chosen = new Map(draft.attacks.map((a) => [a.attackSpecId, a]))
      return {
        ...draft,
        attacks: applyLocks(
          action.attacks.map((a) => {
            const old = chosen.get(a.attackSpecId)
            return {
              ...a,
              trainingSliceId: old?.trainingSliceId ?? a.trainingSliceId,
              mode: old?.mode ?? a.mode,
              search: old?.search ?? a.search,
            }
          }),
          draft.required,
        ),
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

/** Bước hiện tại đủ dữ liệu để sang bước sau chưa. `maxLimitSeconds` của target đang chọn. */
export function canAdvance(
  draft: Draft,
  options: { maxLimitSeconds?: number; levelInputError?: boolean } = {},
): boolean {
  switch (draft.step) {
    case 1:
      return draft.protocolId !== null
    case 2:
      return draft.modelId !== null
    case 3:
      return draft.sliceId !== null && draft.mappingId !== null
    case 4:
      return (
        !options.levelInputError && draft.attacks.length > 0 && draft.attacks.every(attackReady)
      )
    case 5:
      return (
        draft.targetId !== null &&
        draft.limitSeconds !== null &&
        draft.limitSeconds > 0 &&
        (options.maxLimitSeconds === undefined || draft.limitSeconds <= options.maxLimitSeconds)
      )
    case 6:
      return false
  }
}

/**
 * Câu nói rõ còn thiếu gì ở bước hiện tại (hiện cạnh nút "Tiếp" khi nút bị khóa), để người dùng
 * không phải đoán. `null` khi đã đủ.
 */
export function missingHint(
  draft: Draft,
  options: { maxLimitSeconds?: number; levelInputError?: boolean } = {},
): string | null {
  if (canAdvance(draft, options)) return null
  switch (draft.step) {
    case 1:
      return 'Chọn một protocol để đi tiếp.'
    case 2:
      return 'Chọn model bạn muốn kiểm thử.'
    case 3:
      if (draft.sliceId === null) return 'Chọn một slice ảnh để đi tiếp.'
      return 'Chọn class mapping giữa dataset và model.'
    case 4: {
      if (options.levelInputError) return 'Sửa ô level đang báo lỗi rồi đi tiếp.'
      if (draft.attacks.length === 0) return 'Chọn ít nhất một attack.'
      const notReady = draft.attacks.find((a) => !attackReady(a))
      if (notReady?.mode === 'search') return 'Điền đủ các ô của phần tự tìm ngưỡng.'
      if (notReady?.requiresTraining && notReady.trainingSliceId === null)
        return 'Chọn slice huấn luyện cho attack cần train.'
      return 'Thêm ít nhất một level cho mỗi attack đã chọn.'
    }
    case 5:
      if (draft.targetId === null) return 'Chọn máy sẽ chạy experiment.'
      if (
        options.maxLimitSeconds !== undefined &&
        draft.limitSeconds !== null &&
        draft.limitSeconds > options.maxLimitSeconds
      )
        return 'Giới hạn thời gian đang vượt mức tối đa của máy này.'
      return 'Đặt giới hạn thời gian lớn hơn 0.'
    case 6:
      return null
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
  }
}

/** Bước chứa trường sai (đường dẫn trường của lỗi 422). */
export function stepOfField(path: string): Step {
  const head = path.split('.')[0]
  if (head === 'protocol_id') return 1
  if (head === 'model_version_id') return 2
  if (head === 'slice_id' || head === 'class_mapping_id') return 3
  if (head === 'attacks') return 4
  if (head === 'compute_target_id' || head === 'limit') return 5
  return 6
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

/** Nháp từ cấu hình nhân bản, mở tại bước 6 (dataset version tra từ slice). */
export function draftFromClone(
  config: ExperimentCreateOutput,
  warnings: CloneWarning[],
  datasetVersionId: string | null,
): Draft {
  // Dừng sớm chỉ áp cho attack quét lưới (Phase 7).
  const stops = config.attacks.filter((a) => a.grid).map((a) => a.grid?.early_stop !== false)
  return {
    step: 6,
    protocolId: config.protocol_id,
    modelId: config.model_version_id,
    datasetVersionId,
    sliceId: config.slice_id,
    mappingId: config.class_mapping_id,
    targetId: config.compute_target_id,
    limitSeconds: Number(config.limit.value),
    attacks: config.attacks.map((a) => ({
      attackSpecId: a.attack_spec_id,
      specSha256: a.spec_sha256,
      levels: [...(a.grid?.levels ?? [])],
      requiresTraining: (a.training_slice_id ?? null) !== null,
      trainingSliceId: a.training_slice_id ?? null,
      mode: a.mode,
      search: a.search ? fromSearchConfig(a.search) : null,
    })),
    earlyStop: stops.every(Boolean),
    earlyStopMixed: stops.some(Boolean) && !stops.every(Boolean),
    name: config.name ?? '',
    clonedFrom: config.cloned_from ?? null,
    cloneWarnings: warnings,
    // Phase 8: khóa theo protocol áp lại khi tải xong protocol (WizardPage).
    required: [],
    requiredFor: null,
    minSliceSize: null,
  }
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
 * Ước lượng hiển thị (bước 5, bước 6, thanh dưới): có attack tìm ngưỡng thì là chi phí tối đa
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
