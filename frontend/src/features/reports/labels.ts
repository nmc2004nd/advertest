/** Nhãn của report (plan task 32). */
import type { ReportStatus, ReportTimelineEvent } from '@/contracts/api'

/** Dải trên trang report, cùng chữ với chân trang PDF. */
export const OFFICIAL = 'BẢN CHÍNH THỨC'

export const REPORT_STATUS_LABEL: Record<ReportStatus, string> = {
  generating: 'Đang sinh',
  ready: 'Sẵn sàng',
  failed: 'Sinh lỗi',
}

export const TIMELINE_LABEL: Record<ReportTimelineEvent['action'], string> = {
  'experiment.submitted': 'Gửi duyệt',
  'review.claimed': 'Nhận review',
  'review.released': 'Trả lại review',
  'review.decided': 'Ra quyết định',
}

export const percent = (value: number | null | undefined): string =>
  value === null || value === undefined ? '—' : `${(value * 100).toFixed(1)}%`

export const decimal = (value: number | null | undefined, digits = 3): string =>
  value === null || value === undefined ? '—' : value.toFixed(digits)
