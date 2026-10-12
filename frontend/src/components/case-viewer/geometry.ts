import type { CSSProperties } from 'react'

import type { CaseBox, CaseDetections } from '@/contracts/api'

/** Ảnh và box ở không gian letterbox 640×640 (tech-stack.md mục 2.1); box là xyxy pixel. */
export const LETTERBOX = 640
export const MATCH_IOU = 0.5

export type Bbox = readonly [number, number, number, number]

export type Layer = 'ground_truth' | 'clean' | 'attacked' | 'ignore_regions'

export const LAYERS: { key: Layer; label: string }[] = [
  { key: 'ground_truth', label: 'Ground truth' },
  { key: 'clean', label: 'Dự đoán ảnh sạch' },
  { key: 'attacked', label: 'Dự đoán sau tấn công' },
  { key: 'ignore_regions', label: 'Vùng bỏ qua' },
]

export const ALL_LAYERS: Record<Layer, boolean> = {
  ground_truth: true,
  clean: true,
  attacked: true,
  ignore_regions: true,
}

export function iou(a: Bbox, b: Bbox): number {
  const w = Math.max(0, Math.min(a[2], b[2]) - Math.max(a[0], b[0]))
  const h = Math.max(0, Math.min(a[3], b[3]) - Math.max(a[1], b[1]))
  const inter = w * h
  const area = (box: Bbox) => Math.max(0, box[2] - box[0]) * Math.max(0, box[3] - box[1])
  const union = area(a) + area(b) - inter
  return union > 0 ? inter / union : 0
}

function detected(gt: CaseBox, predictions: CaseBox[]): boolean {
  return predictions.some(
    (p) => p.class_name === gt.class_name && iou(gt.bbox as Bbox, p.bbox as Bbox) >= MATCH_IOU,
  )
}

/**
 * Chỉ số các ground truth bị mất: được phát hiện đúng trên ảnh sạch (IoU ≥ 0.5, đúng class)
 * nhưng không còn được phát hiện đúng sau tấn công. Giao diện tô đỏ các box này.
 */
export function lostObjects(detections: CaseDetections): number[] {
  return detections.ground_truth.flatMap((gt, i) =>
    detected(gt, detections.clean) && !detected(gt, detections.attacked) ? [i] : [],
  )
}

/** Kích thước bộ đệm canvas theo `devicePixelRatio` để box sắc nét trên màn hình mật độ cao. */
export function canvasSize(cssWidth: number, cssHeight: number, dpr: number) {
  const ratio = Math.max(1, dpr || 1)
  return { width: Math.round(cssWidth * ratio), height: Math.round(cssHeight * ratio), ratio }
}

/** Cả khung letterbox: hiển thị khi không biết vùng ảnh thật. */
export const FULL_VIEW: Bbox = [0, 0, LETTERBOX, LETTERBOX]

/**
 * Vùng hiển thị (tọa độ letterbox): `content_box` để cắt bỏ pad 114 (đề xuất contract 001,
 * Phase R3), hoặc cả khung với dữ liệu cũ (`null`) hay box không hợp lệ.
 */
export function viewOf(contentBox: readonly number[] | null | undefined): Bbox {
  if (!contentBox || contentBox.length !== 4) return FULL_VIEW
  const [x1, y1, x2, y2] = contentBox
  return x2 > x1 && y2 > y1 ? [x1, y1, x2, y2] : FULL_VIEW
}

/** Tỉ lệ CSS `aspect-ratio` của khung hiển thị vùng `view`. */
export function aspectOf(view: Bbox): string {
  return `${view[2] - view[0]} / ${view[3] - view[1]}`
}

/**
 * Style của `<img>` letterbox để vùng `view` lấp đầy khung (khung có tỉ lệ `aspectOf(view)`):
 * phóng ảnh và dịch ngược phần pad ra ngoài khung (`overflow-hidden`).
 */
export function cropStyle(view: Bbox, imageSize = LETTERBOX): CSSProperties {
  const w = view[2] - view[0]
  const h = view[3] - view[1]
  return {
    position: 'absolute',
    maxWidth: 'none',
    width: `${(imageSize / w) * 100}%`,
    height: `${(imageSize / h) * 100}%`,
    left: `${(-view[0] / w) * 100}%`,
    top: `${(-view[1] / h) * 100}%`,
  }
}

/** Box từ pixel ảnh sang pixel CSS của khung hiển thị vùng `view` rộng `cssWidth`. */
export function toCss(box: Bbox, cssWidth: number, view: Bbox = FULL_VIEW): Bbox {
  const s = cssWidth / (view[2] - view[0])
  return [
    (box[0] - view[0]) * s,
    (box[1] - view[1]) * s,
    (box[2] - view[0]) * s,
    (box[3] - view[1]) * s,
  ]
}

/** Điểm CSS trong khung (rộng `cssWidth`) về tọa độ ảnh letterbox. */
export function fromCss(x: number, y: number, cssWidth: number, view: Bbox = FULL_VIEW) {
  const s = (view[2] - view[0]) / cssWidth
  return { x: view[0] + x * s, y: view[1] + y * s }
}

/** Box nhỏ nhất chứa điểm chạm (tọa độ ảnh); ưu tiên box nhỏ vì box lớn hay bao box nhỏ. */
export function hitTest<T extends { bbox: Bbox }>(items: T[], x: number, y: number): T | null {
  const hits = items.filter(({ bbox: b }) => x >= b[0] && x <= b[2] && y >= b[1] && y <= b[3])
  const area = ({ bbox: b }: T) => (b[2] - b[0]) * (b[3] - b[1])
  return hits.sort((a, b) => area(a) - area(b))[0] ?? null
}
