import type { AttackSpec, AttackSpecMetadata, AttackSpecView, PrimaryParam } from '@/contracts/api'

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

/** Nhãn dễ đọc của level từ metadata (`level_labels`, so theo giá trị số); null khi không có. */
export function levelLabel(
  metadata: Pick<AttackSpecMetadata, 'level_labels'> | null | undefined,
  level: number,
): string | null {
  for (const [key, label] of Object.entries(metadata?.level_labels ?? {})) {
    if (Number(key) === level) return label
  }
  return null
}

/**
 * Chip level của một attack ở bước 3 (Phase R3: không có ô gõ level): level đang chọn, level
 * khai nhãn trong metadata, mọi giá trị của tham số rời rạc, và bộ gợi ý. Chỉ giữ giá trị trong
 * dải của spec, sắp tăng dần, tối đa `MAX_LEVELS` cộng các level đang chọn.
 */
export function levelCandidates(
  spec: Pick<AttackSpec, 'primary_param' | 'requires_training'> & {
    metadata?: Pick<AttackSpecMetadata, 'level_labels'> | null
  },
  levels: number[],
): number[] {
  const param = spec.primary_param
  const inRange = (v: number) =>
    param.type === 'discrete' && param.values
      ? param.values.includes(v)
      : v >= param.min && v <= param.max
  const extra = [
    ...Object.keys(spec.metadata?.level_labels ?? {}).map(Number),
    ...(param.type === 'discrete' && param.values ? param.values : []),
    ...suggestedLevels(spec),
  ].filter((v) => Number.isFinite(v) && inRange(v) && !levels.includes(v))
  const unique = [...new Set(extra)].sort((a, b) => a - b)
  return [...levels, ...unique.slice(0, Math.max(0, MAX_LEVELS - levels.length))].sort(
    (a, b) => a - b,
  )
}

/** Tên hiển thị của spec: `display_name` của metadata, chưa có thì tên kỹ thuật. */
export function specTitle(
  spec: Pick<AttackSpecView, 'name' | 'metadata'> | AttackSpec | undefined,
): string {
  if (!spec) return '—'
  return ('metadata' in spec ? spec.metadata?.display_name : undefined) ?? spec.name
}
