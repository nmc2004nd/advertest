/**
 * Trạng thái nháp của wizard (requirements.md Phase 5, Frontend: wizard): thuần, lưu
 * sessionStorage để giữ qua lần tải lại trang, xóa sau khi tạo thành công. Phase 6 thêm slice huấn
 * luyện cho attack cần train (patch) và công tắc dừng sớm.
 */
import type {
  CloneWarning,
  ExperimentCreateInput,
  ExperimentCreateOutput,
  FieldError,
} from '@/contracts/api'

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
/** Phase 6: khóa `v2` vì nháp có thêm trường; nháp `v1` cũ bị bỏ qua (requirements.md Phase 6). */
export const STORAGE_KEY = 'advertest.wizard.v2'

export interface AttackDraft {
  attackSpecId: string
  specSha256: string
  levels: number[]
  /** Spec cần train trên slice huấn luyện trước khi đánh giá (patch, Phase 6). */
  requiresTraining: boolean
  trainingSliceId: string | null
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
}

export type Action =
  | { type: 'go'; step: Step }
  | { type: 'protocol'; id: string }
  | { type: 'model'; id: string }
  | { type: 'datasetVersion'; id: string }
  | { type: 'slice'; id: string }
  | { type: 'mapping'; id: string | null }
  | { type: 'target'; id: string; defaultLimitSeconds: number }
  | { type: 'limit'; seconds: number | null }
  | { type: 'toggleAttack'; attackSpecId: string; specSha256: string; requiresTraining: boolean }
  | { type: 'levels'; attackSpecId: string; levels: number[] }
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
      return { ...draft, protocolId: action.id }
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
      // Giữ slice huấn luyện đã chọn của attack đã có.
      const chosen = new Map(draft.attacks.map((a) => [a.attackSpecId, a.trainingSliceId]))
      return {
        ...draft,
        attacks: action.attacks.map((a) => ({
          ...a,
          trainingSliceId: chosen.get(a.attackSpecId) ?? a.trainingSliceId,
        })),
      }
    }
    case 'levels':
      return {
        ...draft,
        attacks: draft.attacks.map((a) =>
          a.attackSpecId === action.attackSpecId ? { ...a, levels: action.levels } : a,
        ),
      }
    case 'name':
      return { ...draft, name: action.name }
    case 'load':
      return action.draft
  }
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
        !options.levelInputError &&
        draft.attacks.length > 0 &&
        draft.attacks.every(
          (a) => a.levels.length > 0 && (!a.requiresTraining || a.trainingSliceId !== null),
        )
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

/** Ô nhập level đang có giá trị sai ở một attack **đang chọn** (attack đã bỏ chọn không tính). */
export function hasLevelInputError(
  attacks: AttackDraft[],
  inputErrors: Record<string, boolean>,
): boolean {
  return attacks.some((a) => inputErrors[a.attackSpecId] === true)
}

/** Body gửi lên (`ExperimentCreate`); null khi cấu hình chưa đủ để ước lượng hay tạo. */
export function buildBody(draft: Draft): ExperimentCreateInput | null {
  const { protocolId, modelId, sliceId, mappingId, targetId, limitSeconds } = draft
  if (!protocolId || !modelId || !sliceId || !mappingId || !targetId || !limitSeconds) return null
  if (draft.attacks.length === 0 || draft.attacks.some((a) => a.levels.length === 0)) return null
  if (draft.attacks.some((a) => a.requiresTraining && a.trainingSliceId === null)) return null
  return {
    schema_version: 1,
    protocol_id: protocolId,
    model_version_id: modelId,
    slice_id: sliceId,
    class_mapping_id: mappingId,
    compute_target_id: targetId,
    attacks: draft.attacks.map((a) => ({
      schema_version: 1,
      attack_spec_id: a.attackSpecId,
      spec_sha256: a.specSha256,
      mode: 'grid' as const,
      // `early_stop` chỉ gửi khi tắt: mặc định bật, body như Phase 5 (cùng config_sha256).
      grid: draft.earlyStop ? { levels: a.levels } : { levels: a.levels, early_stop: false },
      search: null,
      seed: SEED,
      ...(a.requiresTraining ? { training_slice_id: a.trainingSliceId } : {}),
    })),
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
  const stops = config.attacks.map((a) => a.grid?.early_stop !== false)
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
    })),
    earlyStop: stops.every(Boolean),
    earlyStopMixed: stops.some(Boolean) && !stops.every(Boolean),
    name: config.name ?? '',
    clonedFrom: config.cloned_from ?? null,
    cloneWarnings: warnings,
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
