/**
 * Câu kết luận một dòng phía trên từng biểu đồ của tab Kết quả (requirements.md Phase R3, Kết quả
 * và insight): hàm thuần, sinh theo quy tắc từ đúng dữ liệu của biểu đồ. Câu kết luận chung của
 * experiment lấy từ backend (`conclusion.text`), không sinh ở đây.
 */
import type { AttackRankingEntry, RobustnessRow } from '@/contracts/api'

import { type ComparisonRow, formatNumber } from './breakpoints'
import type { AttackCurve } from './curves'

/** Ngưỡng điểm yếu cố định của contract (`WEAKNESS_DROP`, requirements.md Phase R2, Decisions). */
export const WEAKNESS_DROP = 0.3
/** Dưới mức này coi như không sụt đáng kể (`WEAKNESS_VISIBLE_DROP` của contract). */
export const VISIBLE_DROP = 0.1

/** Phần trăm làm tròn số nguyên, như câu kết luận của backend (0.42 → "42%"). */
export function percent(value: number): string {
  return `${Math.round(value * 100)}%`
}

/** Nhãn một dải cường độ của ma trận: "0–25% dải". */
export function bandLabel([lo, hi]: readonly [number, number]): string {
  return `${Math.round(lo * 100)}–${Math.round(hi * 100)}% dải`
}

export type DropTone = 'empty' | 'none' | 'low' | 'mid' | 'high'

/** Thang màu ô ma trận (design.md mục 3): < 0.1, 0.1–0.3, 0.3–0.5, ≥ 0.5; null là chưa chạy. */
export function dropTone(drop: number | null): DropTone {
  if (drop === null) return 'empty'
  if (drop < VISIBLE_DROP) return 'none'
  if (drop < WEAKNESS_DROP) return 'low'
  if (drop < 0.5) return 'mid'
  return 'high'
}

/** Đường mức sụt của một attack: level đầu tiên sụt từ 30% trở lên, hoặc mức sụt lớn nhất. */
export function curveSentence(curve: AttackCurve): string {
  const points = curve.points.filter((p) => p.relativeDrop !== null)
  const param = curve.paramName
  if (points.length === 0) return `${curve.name}: chưa có level nào có metric.`
  const broken = points.find((p) => (p.relativeDrop ?? 0) >= WEAKNESS_DROP)
  if (broken) {
    return `${curve.name}: từ ${param} ${formatNumber(broken.level)}, mAP@0.5 giảm ${percent(broken.relativeDrop ?? 0)}, vượt mức 30%.`
  }
  const worst = points.reduce((a, b) => ((b.relativeDrop ?? 0) > (a.relativeDrop ?? 0) ? b : a))
  if ((worst.relativeDrop ?? 0) < VISIBLE_DROP) {
    return `${curve.name}: mAP@0.5 giảm dưới 10% ở mọi level đã chạy.`
  }
  return `${curve.name}: mức sụt lớn nhất ${percent(worst.relativeDrop ?? 0)} ở ${param} ${formatNumber(worst.level)}, chưa tới 30%.`
}

/** Xếp hạng attack theo `auc_drop` (thứ tự của backend: giảm dần, không đủ dữ liệu xếp cuối). */
export function rankingSentence(ranking: AttackRankingEntry[]): string {
  const ranked = ranking.filter((e) => e.auc_drop !== null)
  if (ranked.length === 0) return 'Chưa attack nào đủ dữ liệu để xếp hạng.'
  const top = ranked[0]
  if (ranked.length === 1) {
    return `Mới có ${top.name} đủ dữ liệu: diện tích mức sụt ${formatAuc(top.auc_drop)}.`
  }
  const last = ranked[ranked.length - 1]
  return `${top.name} gây hại nhiều nhất trên toàn dải (auc_drop ${formatAuc(top.auc_drop)}), ${last.name} ít nhất (${formatAuc(last.auc_drop)}).`
}

function formatAuc(value: number | null): string {
  return value === null ? '—' : value.toFixed(2)
}

/** So sánh điểm gãy (đã chuẩn hóa về % dải của spec). */
export function breakpointSentence(rows: ComparisonRow[]): string {
  const found = rows.filter(
    (r) => (r.status === 'found' || r.status === 'non_monotonic') && r.value !== null,
  )
  if (found.length > 0) {
    const first = found.reduce((a, b) => ((b.value ?? 0) < (a.value ?? 0) ? b : a))
    const rest = found.length - 1
    return `${first.name} làm model gãy sớm nhất, ở ${first.label} dải của spec${rest > 0 ? `; ${rest} attack khác gãy muộn hơn` : ''}.`
  }
  if (rows.some((r) => r.status === 'below_min')) {
    const name = rows.find((r) => r.status === 'below_min')?.name ?? ''
    return `${name} làm model gãy ngay ở mức nhỏ nhất của dải tìm kiếm.`
  }
  if (rows.some((r) => r.status === 'not_reached')) {
    return 'Chưa attack nào làm model gãy trong dải tìm kiếm.'
  }
  return 'Chưa có điểm gãy nào: tìm ngưỡng chưa xong.'
}

/** Ma trận độ bền: ô sụt nặng nhất, và số attack có ô từ 30% trở lên. */
export function matrixSentence(
  rows: RobustnessRow[],
  bands: readonly (readonly [number, number])[],
  name: (row: RobustnessRow) => string = (row) => row.attack_name,
): string {
  let worst: { row: RobustnessRow; band: number; drop: number } | null = null
  for (const row of rows) {
    for (const cell of row.cells) {
      if (cell.max_relative_drop === null) continue
      if (worst === null || cell.max_relative_drop > worst.drop) {
        worst = { row, band: cell.band, drop: cell.max_relative_drop }
      }
    }
  }
  if (worst === null) return 'Chưa dải nào có run có metric.'
  if (worst.drop < VISIBLE_DROP) return 'Mọi attack đã chạy đều sụt dưới 10% ở mọi dải.'
  const where = `${name(worst.row)} ở dải ${bandLabel(bands[worst.band])}`
  if (worst.drop < WEAKNESS_DROP) {
    return `Mức sụt lớn nhất là ${percent(worst.drop)} (${where}), chưa attack nào tới 30%.`
  }
  const weak = rows.filter((r) =>
    r.cells.some((c) => (c.max_relative_drop ?? 0) >= WEAKNESS_DROP),
  ).length
  return `Sụt nặng nhất ${percent(worst.drop)} (${where}); ${weak}/${rows.length} attack có dải sụt từ 30% trở lên.`
}
