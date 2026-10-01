import type { AttackRankingEntry } from '@/contracts/api'

export const NO_DATA = 'Không đủ dữ liệu'

export function formatAuc(value: number | null): string {
  return value === null ? NO_DATA : value.toFixed(3)
}

/** Số level có kết quả, kèm số level bỏ qua do dừng sớm (được tính bằng level kích hoạt). */
export function levelsText(entry: AttackRankingEntry): string {
  const stopped = entry.levels_early_stopped
  return stopped
    ? `${entry.levels_evaluated} (+${stopped} dừng sớm)`
    : String(entry.levels_evaluated)
}
