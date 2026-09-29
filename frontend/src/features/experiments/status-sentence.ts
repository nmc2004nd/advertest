import type { RunCounts } from '@/contracts/api'

/** Thứ tự và nhãn các phần sau "x/y hoàn thành" (cùng cách viết với email, Phase 5 Group 3). */
const PARTS: [keyof RunCounts, string][] = [
  ['failed', 'lỗi'],
  ['stopped_limit', 'dừng do giới hạn'],
  ['skipped', 'bỏ qua'],
  ['cancelled', 'đã hủy'],
  ['running', 'đang chạy'],
  ['queued', 'chưa chạy'],
]

export function totalRuns(counts: RunCounts): number {
  return Object.values(counts).reduce((sum, n) => sum + n, 0)
}

/** Ví dụ "18/20 hoàn thành, 1 lỗi, 1 dừng do giới hạn"; bỏ phần bằng 0. */
export function statusSentence(counts: RunCounts): string {
  const parts = [`${counts.completed}/${totalRuns(counts)} hoàn thành`]
  for (const [key, label] of PARTS) if (counts[key] > 0) parts.push(`${counts[key]} ${label}`)
  return parts.join(', ')
}
