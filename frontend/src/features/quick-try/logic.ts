/** Logic thuần của trang thử nhanh (requirements.md Phase R3, mục Thử nhanh). */
import type { BoxSet } from '@/components/case-viewer/boxes'
import type {
  AttackSpecView,
  CaseBox,
  ModelSummary,
  QuickTryLevel,
  QuickTryObject,
} from '@/contracts/api'
import type { QuickTryObjectStatus } from '@/contracts/schemas'

/** Giới hạn ảnh của `POST /quick-tries` (10 MB, JPEG/PNG); chặn ở client để không upload thừa. */
export const QUICK_TRY_MAX_BYTES = 10 * 1024 * 1024
export const QUICK_TRY_TYPES = ['image/jpeg', 'image/png'] as const

/** Model chọn được: chỉ `ready`. */
export function readyModels(models: readonly ModelSummary[]): ModelSummary[] {
  return models.filter((m) => m.status === 'ready')
}

/**
 * Attack chọn được với `model`: luôn ẩn attack cần train (patch); ẩn attack cần gradient khi model
 * không hỗ trợ gradient (backend cũng trả 422 cho hai trường hợp này).
 */
export function quickTryAttacks(
  specs: readonly AttackSpecView[],
  model: Pick<ModelSummary, 'supports_gradients'> | null | undefined,
): AttackSpecView[] {
  return specs.filter(
    (s) => s.requires_training !== true && (!s.requires_gradients || !!model?.supports_gradients),
  )
}

/** Lý do không nhận file ảnh; null khi hợp lệ. */
export function imageError(file: Pick<File, 'size' | 'type'>): string | null {
  if (!(QUICK_TRY_TYPES as readonly string[]).includes(file.type))
    return 'Chỉ nhận ảnh JPEG hoặc PNG.'
  if (file.size > QUICK_TRY_MAX_BYTES) return 'Ảnh lớn hơn 10 MB. Chọn ảnh nhỏ hơn.'
  return null
}

const asBox = (o: QuickTryObject, score: number | null): CaseBox => ({
  bbox: o.bbox,
  class_name: o.class_name,
  score,
})

/** Box trên ảnh sạch: các object model thấy trên ảnh sạch (`kept`, `lost`), lớp "dự đoán ảnh sạch". */
export function cleanBoxes(level: Pick<QuickTryLevel, 'objects'>): BoxSet {
  return {
    groundTruth: [],
    predictions: level.objects
      .filter((o) => o.status !== 'new')
      .map((o) => asBox(o, o.clean_score)),
    predictionKind: 'clean',
    ignoreRegions: [],
    lost: [],
  }
}

/**
 * Box trên ảnh bị tấn công (design.md mục 3): `kept` cam liền, `lost` đỏ dày có ×, `new` cam nét
 * đứt. Object bị mất đi qua lớp "object bị mất" của trình vẽ (đặt ở vị trí trên ảnh sạch).
 */
export function attackedBoxes(level: Pick<QuickTryLevel, 'objects'>): BoxSet {
  const lost = level.objects.filter((o) => o.status === 'lost')
  const shown = level.objects.filter((o) => o.status !== 'lost')
  return {
    groundTruth: lost.map((o) => asBox(o, o.clean_score)),
    lost: lost.map((_, i) => i),
    predictions: shown.map((o) => asBox(o, o.attacked_score)),
    predictionKind: 'attacked',
    fresh: shown.flatMap((o, i) => (o.status === 'new' ? [i] : [])),
    ignoreRegions: [],
  }
}

export function statusCounts(
  level: Pick<QuickTryLevel, 'objects'>,
): Record<QuickTryObjectStatus, number> {
  const counts: Record<QuickTryObjectStatus, number> = { kept: 0, lost: 0, new: 0 }
  for (const o of level.objects) counts[o.status] += 1
  return counts
}

/** Nhãn của level trên thanh trượt: nhãn trong metadata kèm giá trị, không có thì tham số = giá trị. */
export function levelText(level: Pick<QuickTryLevel, 'level' | 'label'>, param?: string): string {
  const value = param ? `${param} = ${level.level}` : String(level.level)
  return level.label ? `${level.label} (${value})` : value
}

/** Giờ xóa dạng `HH:MM` theo giờ máy người dùng. */
export function expiryTime(expiresAt: string): string {
  const date = new Date(expiresAt)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(date.getHours())}:${pad(date.getMinutes())}`
}
