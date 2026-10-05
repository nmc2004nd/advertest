import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ChevronLeft, Copy } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'

import { apiSend } from '@/api/client'
import { errorMessage } from '@/api/messages'
import { can } from '@/auth/permissions'
import { useMe } from '@/auth/useMe'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { FormAlert } from '@/components/FormAlert'
import { LoadError } from '@/components/LoadError'
import { PageLoading } from '@/components/PageLoading'
import { Person } from '@/components/Avatar'
import { Button } from '@/components/ui/button'
import type { ExperimentDetail } from '@/contracts/api'

import {
  ACTIVE_EXPERIMENT,
  EXPERIMENTS_KEY,
  experimentKey,
  useExperiment,
  useExperimentRuns,
} from './api'
import { ExperimentStatusSummary } from './ExperimentStatusSummary'
import { humanTime } from './format'
import { ProgressBar } from './ProgressBar'
import { nextStep } from './next-step'
import { NextStepPanel } from './NextStep'
import { ReviewTab } from './ReviewTab'
import { SubmitDialog } from './SubmitDialog'
import { CostTab, FailureCasesTab, ReproTab, ResultsTab, RunsTable } from './tabs'

const TABS = [
  ['overview', 'Tổng quan'],
  ['results', 'Kết quả'],
  ['cases', 'Failure case'],
  ['cost', 'Chi phí'],
  ['repro', 'Tái lập'],
  // Phase 8: chỉ hiện khi đã gửi duyệt.
  ['review', 'Review'],
] as const

type Tab = (typeof TABS)[number][0]

function useCancel(id: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => apiSend<ExperimentDetail>('POST', `/experiments/${id}/cancel`),
    onSuccess: async (detail) => {
      queryClient.setQueryData(experimentKey(id), detail)
      await queryClient.invalidateQueries({ queryKey: EXPERIMENTS_KEY })
    },
  })
}

/** Chi tiết experiment với 5 tab (requirements.md Phase 5, Frontend: danh sách và chi tiết); Phase 8
 * thêm gửi duyệt, dải "Đã khóa", tab Review và "Nhân bản để sửa". */
export function ExperimentDetailPage() {
  const { id = '' } = useParams()
  const [params, setParams] = useSearchParams()
  const requested: Tab = TABS.some(([key]) => key === params.get('tab'))
    ? (params.get('tab') as Tab)
    : 'overview'
  const { data: me } = useMe()
  const experiment = useExperiment(id)
  const runs = useExperimentRuns(id, experiment.data?.status)
  const cancel = useCancel(id)
  const [confirming, setConfirming] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  if (experiment.isPending) return <PageLoading />
  if (experiment.isError) {
    return (
      <div className="p-4 md:p-6">
        <LoadError onRetry={() => void experiment.refetch()} retrying={experiment.isFetching} />
      </div>
    )
  }
  const e = experiment.data
  const isOwner = me?.id === e.owner.id
  const canCancel =
    isOwner && can(me, 'experiment.cancel_own') && ACTIVE_EXPERIMENT.includes(e.status)
  const runList = runs.data ?? []
  // Phase 8: gửi duyệt (chủ sở hữu, experiment completed, protocol không phải dev).
  const canOpenSubmit =
    isOwner &&
    can(me, 'experiment.submit_review') &&
    e.status === 'completed' &&
    e.protocol.status !== 'dev'
  const step = nextStep(e, me, canOpenSubmit)
  const tabs = TABS.filter(([key]) => key !== 'review' || e.review)
  const fixClone = e.status === 'changes_requested'
  const tab: Tab = tabs.some(([key]) => key === requested) ? requested : 'overview'

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6 p-4 md:p-8">
      <header className="hero relative isolate flex flex-col gap-3 overflow-hidden rounded-[20px] px-5 py-5 md:px-7">
        <div aria-hidden className="hero-hex pointer-events-none absolute inset-0 -z-10" />
        <Link
          to="/experiments"
          className="-ml-1 inline-flex min-h-9 items-center gap-1 self-start rounded-full px-2 text-sm font-semibold text-muted-foreground hover:bg-white/70 hover:text-foreground"
        >
          <ChevronLeft className="size-4" aria-hidden="true" />
          Tất cả experiment
        </Link>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex min-w-0 flex-col gap-2">
            <h1 className="min-w-0 text-[clamp(1.5rem,2vw,1.85rem)] leading-tight font-bold tracking-[-0.03em] break-all">
              {e.name}
            </h1>
            <ExperimentStatusSummary experiment={e} />
          </div>
          <div className="flex flex-wrap gap-2">
            {can(me, 'experiment.create') && (
              <Button variant={fixClone ? 'default' : 'outline'} asChild>
                <Link to={`/experiments/new?clone=${e.id}`}>
                  <Copy aria-hidden="true" />
                  {fixClone ? 'Nhân bản để sửa' : 'Nhân bản'}
                </Link>
              </Button>
            )}
            {canCancel && (
              <Button variant="destructive" onClick={() => setConfirming(true)}>
                Hủy experiment
              </Button>
            )}
          </div>
        </div>
        <p className="flex flex-wrap items-center gap-x-1.5 gap-y-1 text-[15px] leading-7 text-muted-foreground">
          <Person name={e.owner.full_name} />
          <span>
            chạy {e.model.name} trên {e.slice.size} ảnh của {e.slice.name}, theo protocol{' '}
            {e.protocol.name}, bằng máy {e.compute_target.name}; {humanTime(e)}.
          </span>
        </p>
      </header>
      <NextStepPanel experiment={e} view={step} onSubmit={() => setSubmitting(true)} />
      {cancel.isError && <FormAlert>{errorMessage(cancel.error)}</FormAlert>}
      <div role="tablist" aria-label="Chi tiết experiment" className="seg self-start">
        {tabs.map(([key, label]) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={tab === key}
            onClick={() => setParams(key === 'overview' ? {} : { tab: key }, { replace: true })}
          >
            {label}
          </button>
        ))}
      </div>
      <section
        role="tabpanel"
        aria-label={tabs.find(([key]) => key === tab)?.[1]}
        className="min-w-0"
      >
        {tab === 'overview' && (
          <div className="space-y-4">
            <OverviewMonitor experiment={e} />
            {runs.isError ? (
              <LoadError onRetry={() => void runs.refetch()} retrying={runs.isFetching} />
            ) : (
              <RunsTable runs={runList} />
            )}
          </div>
        )}
        {tab === 'results' && <ResultsTab experiment={e} runs={runList} />}
        {tab === 'cases' && <FailureCasesTab runs={runList} />}
        {tab === 'cost' && <CostTab experiment={e} runs={runList} />}
        {tab === 'repro' && <ReproTab runs={runList} />}
        {tab === 'review' && <ReviewTab experiment={e} runs={runList} />}
      </section>
      {canOpenSubmit && (
        <SubmitDialog
          experiment={e}
          runs={runList}
          open={submitting}
          onOpenChange={setSubmitting}
        />
      )}
      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title="Hủy experiment?"
        confirmLabel="Hủy experiment"
        destructive
        pending={cancel.isPending}
        onConfirm={() => cancel.mutate(undefined, { onSettled: () => setConfirming(false) })}
      >
        <p className="text-sm">
          {e.name}: run chưa chạy sẽ bị hủy ngay, run đang chạy dừng khi worker nhận lệnh. Kết quả
          đã có được giữ lại. Không hoàn tác được.
        </p>
      </ConfirmDialog>
    </div>
  )
}

/** Tổng quan tiến độ: một câu, một thanh tiến độ, số run theo trạng thái bằng chữ. */
function OverviewMonitor({ experiment: e }: { experiment: ExperimentDetail }) {
  const c = e.run_counts
  const parts = [
    c.completed && `${c.completed} hoàn thành`,
    c.running && `${c.running} đang chạy`,
    c.queued && `${c.queued} đang chờ`,
    c.failed && `${c.failed} thất bại`,
    c.stopped_limit && `${c.stopped_limit} dừng do giới hạn`,
    c.skipped && `${c.skipped} bỏ qua`,
    c.cancelled && `${c.cancelled} đã hủy`,
  ].filter(Boolean)
  return (
    <div className="panel flex flex-col gap-3 p-5">
      <p className="text-[15px]">
        Đã xử lý <b className="tabular-nums">{e.progress.images_done}</b> trên{' '}
        <b className="tabular-nums">{e.progress.images_total}</b> ảnh của mọi run
        {parts.length ? `: ${parts.join(', ')}.` : '.'}
      </p>
      <ProgressBar progress={e.progress} />
      {e.status === 'queued' && e.queue_position !== null && (
        <p className="text-sm text-muted-foreground">
          Đang chờ ở vị trí {e.queue_position} trong hàng đợi của máy {e.compute_target.name}.
        </p>
      )}
    </div>
  )
}
