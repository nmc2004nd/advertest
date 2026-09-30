import { formatDateTime } from '@/admin/format'
import type { ExperimentSummary, RunView } from '@/contracts/api'

/** Thời gian hiển thị: kết thúc lúc nào, hoặc tạo lúc nào khi chưa kết thúc. */
export function timeText(experiment: ExperimentSummary): string {
  return experiment.finished_at
    ? `Kết thúc ${formatDateTime(experiment.finished_at)}`
    : `Tạo ${formatDateTime(experiment.created_at)}`
}

export { formatDuration } from '@/features/wizard/state'

export function runLabel(run: RunView): string {
  const unit = run.attack_spec.param_unit ? ` ${run.attack_spec.param_unit}` : ''
  return `${run.attack_spec.name} · ${run.attack_spec.param_name} ${run.level}${unit}`
}

/** Tải `manifest.json` về máy (tạo file từ JSON đã tải). */
export function downloadJson(data: unknown, filename: string): void {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }),
  )
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}
