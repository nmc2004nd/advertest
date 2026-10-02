import { Link } from 'react-router'

import { formatDateTime } from '@/admin/format'
import { LoadError } from '@/components/LoadError'
import { PageLoading } from '@/components/PageLoading'
import type { ReportView } from '@/contracts/api'
import { MODEL_VERDICT_LABEL } from '@/features/experiments/review-labels'

import { useReports } from './api'
import { REPORT_STATUS_LABEL } from './labels'

function StatusChip({ report }: { report: ReportView }) {
  const tone =
    report.status === 'ready'
      ? 'bg-emerald-100 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200'
      : report.status === 'failed'
        ? 'bg-red-100 text-red-900 dark:bg-red-950 dark:text-red-200'
        : 'bg-muted text-muted-foreground'
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs whitespace-nowrap ${tone}`}>
      {REPORT_STATUS_LABEL[report.status]}
    </span>
  )
}

const HEADERS = ['Experiment', 'Kết luận về model', 'Người duyệt', 'Ngày duyệt', 'Trạng thái']

/** Bảng: từ 1280px (desktop). */
function ReportTable({ reports }: { reports: ReportView[] }) {
  return (
    <div className="hidden overflow-x-auto rounded-xl border border-border xl:block">
      <table className="w-full text-left text-sm">
        <caption className="sr-only">Report</caption>
        <thead className="bg-muted/50">
          <tr>
            {HEADERS.map((h) => (
              <th key={h} scope="col" className="px-3 py-2 font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {reports.map((r) => (
            <tr key={r.id} className="border-t border-border align-top">
              <td className="px-3 py-2">
                <Link to={`/reports/${r.id}`} className="font-medium hover:underline">
                  {r.experiment_name}
                </Link>
              </td>
              <td className="px-3 py-2">{MODEL_VERDICT_LABEL[r.model_verdict]}</td>
              <td className="px-3 py-2">{r.approved_by.full_name}</td>
              <td className="px-3 py-2">{formatDateTime(r.approved_at)}</td>
              <td className="px-3 py-2">
                <StatusChip report={r} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** Thẻ: điện thoại và tablet. */
function ReportCards({ reports }: { reports: ReportView[] }) {
  return (
    <ul className="grid gap-3 xl:hidden">
      {reports.map((r) => (
        <li key={r.id}>
          <Link
            to={`/reports/${r.id}`}
            className="flex min-h-11 flex-col gap-1 rounded-xl border border-border p-4 hover:bg-muted"
          >
            <span className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-medium break-all">{r.experiment_name}</span>
              <StatusChip report={r} />
            </span>
            <span className="text-sm">{MODEL_VERDICT_LABEL[r.model_verdict]}</span>
            <span className="text-sm text-muted-foreground">
              {r.approved_by.full_name} · {formatDateTime(r.approved_at)}
            </span>
          </Link>
        </li>
      ))}
    </ul>
  )
}

/** Danh sách report, mới nhất trước (requirements.md Phase 8, Frontend; plan task 32). */
export function ReportsPage() {
  const reports = useReports()
  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-4 p-4 md:p-6">
      <h1 className="text-2xl font-semibold">Report</h1>
      <p className="text-sm text-muted-foreground">
        Report chính thức chỉ có sau khi reviewer chấp nhận bài test; nội dung không đổi sau khi
        sinh.
      </p>
      {reports.isPending ? (
        <PageLoading />
      ) : reports.isError ? (
        <LoadError onRetry={() => void reports.refetch()} retrying={reports.isFetching} />
      ) : reports.data.length === 0 ? (
        <p className="text-muted-foreground">Chưa có report nào.</p>
      ) : (
        <>
          <ReportTable reports={reports.data} />
          <ReportCards reports={reports.data} />
        </>
      )}
    </div>
  )
}
