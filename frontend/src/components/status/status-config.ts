import {
  Activity,
  BadgeCheck,
  Ban,
  CircleCheck,
  CircleX,
  Clock,
  Eye,
  FilePen,
  LoaderCircle,
  type LucideIcon,
  OctagonPause,
  PencilLine,
  Send,
  ShieldCheck,
  SkipForward,
  Target,
  TriangleAlert,
} from 'lucide-react'

import type { ExperimentStatus, RunStatus, SearchStatus } from '@/contracts/schemas'

/** Tông màu của badge; mỗi tông có màu riêng cho giao diện sáng và tối. */
export type StatusTone = 'neutral' | 'info' | 'success' | 'warning' | 'danger' | 'muted'

export interface StatusDisplay {
  label: string
  icon: LucideIcon
  tone: StatusTone
}

// Record bắt buộc đủ mọi giá trị: thêm trạng thái mới vào contract mà quên ở đây thì tsc báo lỗi.
export const RUN_STATUS: Record<RunStatus, StatusDisplay> = {
  queued: { label: 'Đang chờ', icon: Clock, tone: 'neutral' },
  running: { label: 'Đang chạy', icon: LoaderCircle, tone: 'info' },
  completed: { label: 'Hoàn thành', icon: CircleCheck, tone: 'success' },
  failed: { label: 'Thất bại', icon: CircleX, tone: 'danger' },
  skipped: { label: 'Bỏ qua', icon: SkipForward, tone: 'muted' },
  stopped_limit: { label: 'Dừng do giới hạn', icon: OctagonPause, tone: 'warning' },
  cancelled: { label: 'Đã hủy', icon: Ban, tone: 'muted' },
}

export const EXPERIMENT_STATUS: Record<ExperimentStatus, StatusDisplay> = {
  draft: { label: 'Nháp', icon: FilePen, tone: 'neutral' },
  queued: { label: 'Đang chờ', icon: Clock, tone: 'neutral' },
  running: { label: 'Đang chạy', icon: LoaderCircle, tone: 'info' },
  completed: { label: 'Hoàn thành', icon: CircleCheck, tone: 'success' },
  submitted_for_review: { label: 'Đã gửi duyệt', icon: Send, tone: 'info' },
  in_review: { label: 'Đang duyệt', icon: Eye, tone: 'info' },
  approved: { label: 'Đã duyệt', icon: BadgeCheck, tone: 'success' },
  changes_requested: { label: 'Yêu cầu sửa', icon: PencilLine, tone: 'warning' },
  rejected: { label: 'Từ chối', icon: CircleX, tone: 'danger' },
  cancelled: { label: 'Đã hủy', icon: Ban, tone: 'muted' },
}

export const SEARCH_STATUS: Record<SearchStatus, StatusDisplay> = {
  found: { label: 'Tìm thấy điểm gãy', icon: Target, tone: 'warning' },
  not_reached: { label: 'Chưa chạm ngưỡng', icon: ShieldCheck, tone: 'success' },
  below_min: { label: 'Gãy ngay mức nhỏ nhất', icon: TriangleAlert, tone: 'danger' },
  stopped_limit: { label: 'Dừng do giới hạn', icon: OctagonPause, tone: 'warning' },
  non_monotonic: { label: 'Không đơn điệu', icon: Activity, tone: 'warning' },
  failed: { label: 'Thất bại', icon: CircleX, tone: 'danger' },
}

export type StatusBadgeProps =
  | { kind: 'run'; status: RunStatus }
  | { kind: 'experiment'; status: ExperimentStatus }
  | { kind: 'search'; status: SearchStatus }

export function statusDisplay(props: StatusBadgeProps): StatusDisplay {
  switch (props.kind) {
    case 'run':
      return RUN_STATUS[props.status]
    case 'experiment':
      return EXPERIMENT_STATUS[props.status]
    case 'search':
      return SEARCH_STATUS[props.status]
  }
}

export const TONE_CLASS: Record<StatusTone, string> = {
  neutral: 'bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-100',
  info: 'bg-sky-100 text-sky-900 dark:bg-sky-950 dark:text-sky-200',
  success: 'bg-emerald-100 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200',
  warning: 'bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200',
  danger: 'bg-red-100 text-red-900 dark:bg-red-950 dark:text-red-200',
  muted: 'bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300',
}
