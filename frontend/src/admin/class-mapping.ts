import type { DifficultyFilter } from '@/contracts/api'

/** Class đích: tên class của model, `null` là bỏ (thành ignore region `unmapped:<class>`). */
export type MappingClasses = Record<string, string | null>

/**
 * Preset `kitti-coco`, chép từ `ml_core/data/mapping.py` (`PRESETS`). Backend suy ra `preset` khi
 * nội dung mapping trùng preset này, nên hai bản phải giống nhau.
 */
export const KITTI_COCO: MappingClasses = {
  Car: 'car',
  Van: 'car',
  Truck: 'truck',
  Pedestrian: 'person',
  Person_sitting: 'person',
  Cyclist: null,
  Tram: null,
  Misc: null,
}

/** Mức Moderate của KITTI (`KITTI_MODERATE` trong `ml_core/data/mapping.py`). */
export const KITTI_MODERATE: DifficultyFilter = {
  min_height_px: 25,
  max_occluded: 1,
  max_truncated: 0.3,
}

const key = (name: string) => name.trim().toLowerCase()

/**
 * Gợi ý mapping cho mỗi class của dataset: theo preset `kitti-coco` khi có class đích tương ứng
 * trong model, không thì class model trùng tên (không phân biệt hoa thường), còn lại bỏ.
 */
export function suggestMapping(
  datasetClasses: readonly string[],
  modelClasses: readonly string[],
): MappingClasses {
  const byKey = new Map(modelClasses.map((name) => [key(name), name]))
  return Object.fromEntries(
    datasetClasses.map((source) => {
      if (source in KITTI_COCO) {
        const target = KITTI_COCO[source]
        return [source, target === null ? null : (byKey.get(key(target)) ?? null)]
      }
      return [source, byKey.get(key(source)) ?? null]
    }),
  )
}

/** Gợi ý, đè bằng lựa chọn của người dùng (bỏ lựa chọn không còn hợp lệ khi đổi model/dataset). */
export function effectiveMapping(
  suggested: MappingClasses,
  overrides: MappingClasses,
  modelClasses: readonly string[],
): MappingClasses {
  const valid = new Set(modelClasses)
  const result: MappingClasses = { ...suggested }
  for (const [source, target] of Object.entries(overrides)) {
    if (source in result && (target === null || valid.has(target))) result[source] = target
  }
  return result
}

/** Lỗi của mapping (contract `ClassMappingCreate`): cần ít nhất một class được map. */
export function mappingError(classes: MappingClasses): string | null {
  if (Object.keys(classes).length === 0) return 'Dataset này chưa có class nào.'
  return Object.values(classes).some((target) => target !== null)
    ? null
    : 'Chọn class của model cho ít nhất một class của dataset.'
}

/** Số class gốc được map, để tóm tắt mapping. */
export function mappedCount(classes: MappingClasses): number {
  return Object.values(classes).filter((target) => target !== null).length
}
