import type { CaseBox, CaseIgnoreRegion } from '@/contracts/api'

import type { Bbox } from './geometry'

/** Màu cố định (vẽ trên ảnh chụp, không theo theme): dễ phân biệt cả ở chế độ sáng và tối. */
export const BOX_COLORS = {
  ground_truth: '#22c55e',
  clean: '#3b82f6',
  attacked: '#f97316',
  ignore_regions: '#a3a3a3',
  lost: '#ef4444',
} as const

type Kind = keyof typeof BOX_COLORS

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
}

/** Màn hình từ breakpoint md (768px, tech-stack.md mục 5.1) hiện sẵn nhãn box; nhỏ hơn thì
 * chạm vào box để hiện (tính theo màn hình, không theo bề rộng khung ảnh). */
export const LABELS_MEDIA_QUERY = '(min-width: 768px)'

export function boxesOf(set: BoxSet): DrawBox[] {
  const lost = new Set(set.lost)
  return [
    ...set.ignoreRegions.map((r) => ({
      bbox: r.bbox as Bbox,
      kind: 'ignore_regions' as const,
      label: `Bỏ qua: ${r.source}`,
    })),
    ...set.groundTruth.map((b, i) => ({
      bbox: b.bbox as Bbox,
      kind: lost.has(i) ? ('lost' as const) : ('ground_truth' as const),
      label: lost.has(i) ? `${b.class_name} (bị mất)` : b.class_name,
    })),
    ...set.predictions.map((b) => ({
      bbox: b.bbox as Bbox,
      kind: set.predictionKind,
      label: `${b.class_name} ${(b.score ?? 0).toFixed(2)}`,
    })),
  ]
}
