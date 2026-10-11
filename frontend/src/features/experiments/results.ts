/** Hàm thuần của tab Kết quả Phase R3 (insight, lọc failure case, nâng lên chính thức). */
import type { AttackSpec, ExperimentDetail, RunView } from '@/contracts/api'
import { specTitle } from '@/features/wizard/levels'

/** Tên hiển thị của attack theo catalog (metadata), không có thì tên kỹ thuật. */
export function displayNames(catalog: AttackSpec[]): (id: string, fallback: string) => string {
  const byId = new Map(catalog.map((spec) => [spec.id, specTitle(spec)]))
  return (id, fallback) => byId.get(id) ?? fallback
}

/** Run khớp bộ lọc `?attack=<tên spec>&level=<level>` (bấm điểm yếu ở tab Kết quả, Phase R3). */
export function filterRuns(
  runs: RunView[],
  attack: string | null,
  level: string | null,
): RunView[] {
  return runs.filter(
    (run) =>
      (attack === null || run.attack_spec.name === attack) &&
      (level === null || run.level === Number(level)),
  )
}

export const PROMOTE_LABEL = 'Nâng lên chính thức'

/** Câu giải thích khi `promote` trả 409 (design.md mục 7: chuyện gì xảy ra và cách sửa). */
export const PROMOTE_CONFLICT =
  'Chỉ nâng được experiment Khám phá đã kết thúc sang protocol đang dùng. Tải lại trang để xem trạng thái mới, hoặc chọn protocol khác.'

/** Nút chỉ hiện với experiment Khám phá đã kết thúc (`completed` hoặc `cancelled`). */
export function canPromote(experiment: Pick<ExperimentDetail, 'mode' | 'status'>): boolean {
  return (
    experiment.mode === 'exploration' &&
    (experiment.status === 'completed' || experiment.status === 'cancelled')
  )
}
