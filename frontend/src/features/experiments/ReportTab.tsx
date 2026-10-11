import { FileText } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router'

import { formatDateTime } from '@/admin/format'
import { EmptyState } from '@/components/EmptyState'
import { Button } from '@/components/ui/button'
import type { ExperimentDetail } from '@/contracts/api'
import { REPORT_STATUS_LABEL } from '@/features/reports/labels'

import { MODEL_VERDICT_LABEL, OPEN_REVIEW } from './review-labels'

/** Trạng thái trống: điều gì còn thiếu cho report và việc tiếp theo (design.md mục 6). */
function missing(e: ExperimentDetail): { title: string; body: string } {
  if (e.mode === 'exploration') {
    return {
      title: 'Experiment Khám phá không có report',
      body: 'Report chỉ xuất từ experiment Chính thức đã được chấp nhận. Kết quả Khám phá chỉ được liệt kê ở mục Lịch sử của report.',
    }
  }
  if (OPEN_REVIEW.includes(e.status)) {
    return {
      title: 'Chưa có report',
      body: 'Experiment đang chờ review. Report chính thức được sinh ngay khi reviewer chấp nhận.',
    }
  }
  switch (e.status) {
    case 'approved':
      return { title: 'Đang sinh report', body: 'Report chính thức sẽ có sau ít phút.' }
    case 'changes_requested':
      return {
        title: 'Không có report',
        body: 'Reviewer yêu cầu sửa. Nhân bản experiment, sửa theo lý do trong tab Review rồi gửi duyệt lại.',
      }
    case 'rejected':
      return {
        title: 'Không có report',
        body: 'Reviewer đã từ chối experiment này. Lý do nằm trong tab Review.',
      }
    case 'cancelled':
      return {
        title: 'Không có report',
        body: 'Experiment đã hủy nên không gửi duyệt được. Nhân bản để chạy lại.',
      }
    default:
      return {
        title: 'Chưa có report',
        body: 'Report chính thức được sinh khi reviewer chấp nhận experiment. Gửi duyệt khi mọi run bắt buộc đã xong.',
      }
  }
}

/** Tab Report (requirements.md Phase R3, mục Trang experiment): luôn hiện. */
export function ReportTab({
  experiment: e,
  action,
}: {
  experiment: ExperimentDetail
  /** Nút hành động tiếp theo của trạng thái trống (trang chi tiết quyết định). */
  action?: ReactNode
}) {
  const report = e.report
  if (!report) {
    const { title, body } = missing(e)
    return (
      <EmptyState icon={FileText} title={title} action={action}>
        {body}
      </EmptyState>
    )
  }
  return (
    <div className="panel flex flex-col gap-4 p-5" data-testid="report-summary">
      <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1 text-sm">
        <dt className="text-muted-foreground">Trạng thái</dt>
        <dd>{REPORT_STATUS_LABEL[report.status]}</dd>
        <dt className="text-muted-foreground">Kết luận về model</dt>
        <dd>{MODEL_VERDICT_LABEL[report.model_verdict]}</dd>
        <dt className="text-muted-foreground">Người duyệt</dt>
        <dd className="min-w-0 break-words">
          {report.approved_by.full_name}, {formatDateTime(report.approved_at)}
        </dd>
      </dl>
      <Button asChild className="self-start">
        <Link to={`/reports/${report.id}`}>Mở report chính thức</Link>
      </Button>
    </div>
  )
}
