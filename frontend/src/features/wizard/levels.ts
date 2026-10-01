import type { AttackSpec, PrimaryParam } from '@/contracts/api'

import type { AttackDraft } from './state'

/** Tối đa 12 level mỗi attack (requirements.md Phase 5, Kiểm tra khi tạo). */
export const MAX_LEVELS = 12

function format(value: number): string {
  return String(Number(value.toFixed(6)))
}

/** Mô tả dải hợp lệ của tham số chính, ví dụ "0–32 1/255" hoặc "1, 2, 3". */
export function rangeText(param: PrimaryParam): string {
  const unit = param.unit ? ` ${param.unit}` : ''
  if (param.type === 'discrete' && param.values) return param.values.map(format).join(', ') + unit
  return `${format(param.min)}–${format(param.max)}${unit}`
}

/**
 * Lỗi khi thêm `raw` vào danh sách level (null nếu hợp lệ): phải là số, trong dải của spec
 * (spec rời rạc thì thuộc danh sách giá trị), không trùng, không quá 12 level.
 */
export function levelError(param: PrimaryParam, levels: number[], raw: string): string | null {
  const text = raw.trim().replace(',', '.')
  if (text === '') return 'Nhập một giá trị'
  const value = Number(text)
  if (!Number.isFinite(value)) return `"${raw.trim()}" không phải là số`
  const inRange =
    param.type === 'discrete' && param.values
      ? param.values.includes(value)
      : value >= param.min && value <= param.max
  if (!inRange) return `Level ${format(value)} ngoài dải ${rangeText(param)}`
  if (levels.includes(value)) return `Level ${format(value)} đã có`
  if (levels.length >= MAX_LEVELS) return `Tối đa ${MAX_LEVELS} level mỗi attack`
  return null
}

export function parseLevel(raw: string): number {
  return Number(raw.trim().replace(',', '.'))
}

/** Thêm level và giữ thứ tự tăng dần. */
export function addLevel(levels: number[], value: number): number[] {
  return [...levels, value].sort((a, b) => a - b)
}

/**
 * Bộ level gợi ý: spec rời rạc → mọi giá trị; liên tục → các lũy thừa của 2 trong dải (ví dụ eps
 * 2, 4, 8, 16), nếu ít hơn 2 giá trị thì 4 điểm chia đều dải.
 */
export function presetLevels(param: PrimaryParam): number[] {
  if (param.type === 'discrete' && param.values) return [...param.values].slice(0, MAX_LEVELS)
  const powers = [1, 2, 4, 8, 16, 32, 64].filter((v) => v > param.min && v <= param.max).slice(-4)
  if (powers.length >= 2) return powers
  return [1, 2, 3, 4].map((k) => Number((param.min + ((param.max - param.min) * k) / 4).toFixed(3)))
}

/** Phase 6: patch chọn 2 `area_ratio` 0.1 và 0.25, mỗi giá trị train một patch (kickoff). */
export const PATCH_PRESET_LEVELS = [0.1, 0.25]

/** Bộ level gợi ý của một spec: spec cần train dùng `PATCH_PRESET_LEVELS` (trong dải). */
export function suggestedLevels(spec: Pick<AttackSpec, 'primary_param' | 'requires_training'>) {
  const param = spec.primary_param
  if (spec.requires_training) {
    return PATCH_PRESET_LEVELS.filter((v) => v >= param.min && v <= param.max)
  }
  return presetLevels(param)
}

/** Preset "Toàn bộ catalog" (requirements.md Phase 6, Frontend): mọi spec với level gợi ý. */
export function catalogPreset(specs: AttackSpec[]): AttackDraft[] {
  return specs.map((spec) => ({
    attackSpecId: spec.id,
    specSha256: spec.spec_sha256,
    levels: suggestedLevels(spec),
    requiresTraining: spec.requires_training === true,
    trainingSliceId: null,
    mode: 'grid' as const,
    search: null,
  }))
}
