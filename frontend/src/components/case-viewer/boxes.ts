import type { CaseBox, CaseIgnoreRegion } from '@/contracts/api'

import type { Bbox } from './geometry'

/** Màu cố định (vẽ trên ảnh chụp, không theo theme): dễ phân biệt cả ở chế độ sáng và tối. */
export const BOX_COLORS = {
  ground_truth: '#22c55e',
  clean: '#3b82f6',
  attacked: '#f97316',
  ignore_regions: '#a3a3a3',
  lost: '#ef4444',
  fresh: '#f97316',
} as const

type Kind = keyof typeof BOX_COLORS

/** Kiểu nét của từng lớp (design.md mục 3): màu luôn đi kèm kiểu nét hoặc ký hiệu, để người mù
 * màu vẫn phân biệt được. `dash` rỗng là nét liền. */
export const BOX_STROKE: Record<Kind, { width: number; dash: number[] }> = {
  ground_truth: { width: 2, dash: [8, 4] },
  clean: { width: 2, dash: [] },
  attacked: { width: 2, dash: [] },
  ignore_regions: { width: 2, dash: [4, 3] },
  lost: { width: 3, dash: [] },
  fresh: { width: 2, dash: [3, 3] },
}

/** Ký hiệu đứng đầu nhãn của object bị mất. */
export const LOST_MARK = '×'

export interface DrawBox {
  bbox: Bbox
  kind: Kind
  label: string
}

export interface BoxSet {
  groundTruth: CaseBox[]
  predictions: CaseBox[]
  predictionKind: 'clean' | 'attacked'
  ignoreRegions: CaseIgnoreRegion[]
  /** Chỉ số ground truth bị mất (tô đỏ). */
  lost: number[]
  /** Chỉ số dự đoán là phát hiện sai mới sau tấn công (thử nhanh, Phase R3). */
  fresh?: number[]
}

/** Màn hình từ breakpoint md (768px, tech-stack.md mục 5.1) hiện sẵn nhãn box; nhỏ hơn thì
 * chạm vào box để hiện (tính theo màn hình, không theo bề rộng khung ảnh). */
export const LABELS_MEDIA_QUERY = '(min-width: 768px)'

export function boxesOf(set: BoxSet): DrawBox[] {
  const lost = new Set(set.lost)
  const fresh = new Set(set.fresh ?? [])
  return [
    ...set.ignoreRegions.map((r) => ({
      bbox: r.bbox as Bbox,
      kind: 'ignore_regions' as const,
      label: `Bỏ qua: ${r.source}`,
    })),
    ...set.groundTruth.map((b, i) => ({
      bbox: b.bbox as Bbox,
      kind: lost.has(i) ? ('lost' as const) : ('ground_truth' as const),
      label: lost.has(i) ? `${LOST_MARK} ${b.class_name} (bị mất)` : b.class_name,
    })),
    ...set.predictions.map((b, i) => ({
      bbox: b.bbox as Bbox,
      kind: fresh.has(i) ? ('fresh' as const) : set.predictionKind,
      label: fresh.has(i)
        ? `${b.class_name} ${(b.score ?? 0).toFixed(2)} (mới)`
        : `${b.class_name} ${(b.score ?? 0).toFixed(2)}`,
    })),
  ]
}
