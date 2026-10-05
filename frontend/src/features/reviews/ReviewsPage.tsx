import { Link, useSearchParams } from 'react-router'

import { formatDateTime } from '@/admin/format'
import { LoadError } from '@/components/LoadError'
import { PageLoading } from '@/components/PageLoading'
import { StatusBadge } from '@/components/status/StatusBadge'
import type { ReviewQueueFilter, ReviewQueueItem } from '@/contracts/api'
import { DECISION_LABEL } from '@/features/experiments/review-labels'

import { type QueueSort, useReviewQueue } from './api'
import { PageHero } from '@/layout/PageHero'
import { ReviewArt } from '@/layout/hero-art'

const GROUPS: [ReviewQueueFilter, string][] = [
  ['waiting', 'Chờ nhận'],
  ['mine', 'Tôi đang review'],
  ['decided', 'Đã quyết định'],
]
const SORTS: [QueueSort, string][] = [
  ['submitted_at', 'Thời gian gửi'],
  ['max_drop', 'Mức sụt lớn nhất'],
]

function dropText(item: ReviewQueueItem): string {
  return item.max_relative_drop === null || item.max_relative_drop === undefined
    ? '—'
    : `${Math.round(item.max_relative_drop * 100)}%`
}

function progressText(item: ReviewQueueItem): string {
  return `${item.required_cases_reviewed}/${item.required_cases_total} case đã review`
}

function stateText(item: ReviewQueueItem): string {
  if (item.decision) return DECISION_LABEL[item.decision]
  return item.assignee ? `Đang review: ${item.assignee.full_name}` : 'Chưa có người nhận'
}

/** Bảng: từ 1280px (desktop). */
function QueueTable({ items }: { items: ReviewQueueItem[] }) {
  const headers = [
    'Experiment',
    'Protocol',
    'Người tạo',
    'Gửi lúc',
    'Mức sụt lớn nhất',
    'Tiến độ',
    'Trạng thái',
  ]
  return (
    <div className="hidden overflow-x-auto rounded-xl border border-border bg-surface-solid xl:block">
      <table className="w-full text-left text-sm">
        <caption className="sr-only">Hàng đợi review</caption>
        <thead className="bg-muted/50">
          <tr>
            {headers.map((h) => (
              <th key={h} scope="col" className="px-3 py-2 font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.experiment.id} className="border-t border-border align-top">
              <td className="px-3 py-2">
                <Link to={`/reviews/${item.experiment.id}`} className="font-medium hover:underline">
                  {item.experiment.name}
                </Link>
              </td>
              <td className="px-3 py-2">{item.protocol.name}</td>
              <td className="px-3 py-2">{item.experiment.owner.full_name}</td>
              <td className="px-3 py-2">{formatDateTime(item.submitted_at)}</td>
              <td className="px-3 py-2 tabular-nums">{dropText(item)}</td>
              <td className="px-3 py-2">{progressText(item)}</td>
              <td className="px-3 py-2">
                <StatusBadge kind="experiment" status={item.experiment.status} />
                <span className="mt-1 block text-muted-foreground">{stateText(item)}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** Thẻ: điện thoại và tablet. */
function QueueCards({ items }: { items: ReviewQueueItem[] }) {
  return (
    <ul className="grid gap-3 xl:hidden">
      {items.map((item) => (
        <li key={item.experiment.id}>
          <Link
            to={`/reviews/${item.experiment.id}`}
            className="flex min-h-11 flex-col gap-1 rounded-xl border border-border bg-surface-solid p-4 hover:bg-muted"
          >
            <span className="font-medium break-all">{item.experiment.name}</span>
            <span className="text-sm text-muted-foreground">
              {item.protocol.name} · {item.experiment.owner.full_name} ·{' '}
              {formatDateTime(item.submitted_at)}
            </span>
            <span className="flex flex-wrap items-center gap-2 text-sm">
              <StatusBadge kind="experiment" status={item.experiment.status} />
              Mức sụt lớn nhất {dropText(item)} · {progressText(item)}
            </span>
            <span className="text-sm text-muted-foreground">{stateText(item)}</span>
          </Link>
        </li>
      ))}
    </ul>
  )
}

/** Hàng đợi review (requirements.md Phase 8, Frontend reviewer; plan task 27). */
export function ReviewsPage() {
  const [params, setParams] = useSearchParams()
  const group = GROUPS.find(([g]) => g === params.get('status'))?.[0] ?? 'waiting'
  const sort = SORTS.find(([s]) => s === params.get('sort'))?.[0] ?? 'submitted_at'
  const queue = useReviewQueue(group, sort)
  const set = (next: { status?: string; sort?: string }) =>
    setParams({ status: group, sort, ...next }, { replace: true })

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-5 p-4 md:p-8">
      <PageHero
        art={<ReviewArt />}
        title="Duyệt"
        description="Xem các case bắt buộc, ghi verdict rồi quyết định. Không gồm experiment do bạn tạo: người chạy test không duyệt test của mình."
      />
      <div role="tablist" aria-label="Nhóm hàng đợi" className="seg self-start">
        {GROUPS.map(([key, label]) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={group === key}
            onClick={() => set({ status: key })}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="flex max-w-xs flex-col gap-1.5">
        <label htmlFor="sap-xep-hang-doi" className="text-sm font-medium">
          Sắp xếp
        </label>
        <select
          id="sap-xep-hang-doi"
          value={sort}
          onChange={(event) => set({ sort: event.target.value })}
          className="min-h-11 rounded-[14px] border border-line bg-field text-foreground outline-none backdrop-blur transition-[border-color,box-shadow] duration-200 placeholder:text-muted-foreground/70 hover:border-input focus-visible:border-cta/70 focus-visible:ring-4 focus-visible:ring-cta/15 px-3 text-base"
        >
          {SORTS.map(([key, label]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
        </select>
      </div>
      {queue.isPending ? (
        <PageLoading />
      ) : queue.isError ? (
        <LoadError onRetry={() => void queue.refetch()} retrying={queue.isFetching} />
      ) : queue.data.length === 0 ? (
        <p className="text-muted-foreground">Không có experiment nào trong nhóm này.</p>
      ) : (
        <>
          <QueueTable items={queue.data} />
          <QueueCards items={queue.data} />
        </>
      )}
    </div>
  )
}
