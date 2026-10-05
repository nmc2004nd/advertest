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

/** Nhãn của run bị bỏ do dừng sớm (requirements.md Phase 6, Frontend: bảng run). */
export const EARLY_STOP_TEXT = 'Bỏ qua: model đã sụp ở level thấp hơn'

/** Lý do trạng thái hiển thị cho run; `early_stop` ghi rõ level đã kích hoạt (nếu tìm thấy). */
export function reasonText(run: RunView, runs: RunView[]): string | null {
  const reason = run.status_reason
  if (!reason) return null
  if (reason.code !== 'early_stop') return reason.message
  const trigger = runs.find((r) => r.run_id === reason.trigger_run_id)
  if (!trigger) return EARLY_STOP_TEXT
  const unit = trigger.attack_spec.param_unit ? ` ${trigger.attack_spec.param_unit}` : ''
  return `${EARLY_STOP_TEXT} (sụp ở ${trigger.attack_spec.param_name} ${trigger.level}${unit})`
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

/** Thời gian tương đối dễ đọc: "vừa xong", "5 phút trước", "hôm qua lúc 14:20". */
export function relativeTime(iso: string, now: Date = new Date()): string {
  const then = new Date(iso)
  const minutes = Math.round((now.getTime() - then.getTime()) / 60000)
  if (minutes < 1) return 'vừa xong'
  if (minutes < 60) return `${minutes} phút trước`
  const hours = Math.round(minutes / 60)
  const time = then.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' })
  const sameDay = then.toDateString() === now.toDateString()
  if (sameDay) return hours < 6 ? `${hours} giờ trước` : `hôm nay lúc ${time}`
  const yesterday = new Date(now)
  yesterday.setDate(now.getDate() - 1)
  if (then.toDateString() === yesterday.toDateString()) return `hôm qua lúc ${time}`
  return formatDateTime(iso)
}

/** Câu thời gian của experiment theo giọng người: "xong 5 phút trước", "tạo hôm qua lúc 9:10". */
export function humanTime(experiment: ExperimentSummary): string {
  return experiment.finished_at
    ? `xong ${relativeTime(experiment.finished_at)}`
    : `tạo ${relativeTime(experiment.created_at)}`
}
