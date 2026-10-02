import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Copy, Lock, Send } from 'lucide-react'
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
import { Button } from '@/components/ui/button'
import type { ExperimentDetail } from '@/contracts/api'
import { cn } from '@/lib/utils'

import {
  ACTIVE_EXPERIMENT,
  EXPERIMENTS_KEY,
  experimentKey,
  useExperiment,
  useExperimentRuns,
} from './api'
import { ExperimentStatusSummary } from './ExperimentStatusSummary'
import { timeText } from './format'
import { ProgressBar } from './ProgressBar'
import { lockedBannerText } from './review-labels'
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
  const banner = lockedBannerText(e.status)
  const tabs = TABS.filter(([key]) => key !== 'review' || e.review)
  const fixClone = e.status === 'changes_requested'
  const tab: Tab = tabs.some(([key]) => key === requested) ? requested : 'overview'

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-4 p-4 md:p-6">
      <header className="flex flex-col gap-2">
        <Link to="/experiments" className="text-sm text-muted-foreground hover:underline">
          ← Experiment
        </Link>
        <div className="flex flex-wrap items-start justify-between gap-2">
          <h1 className="min-w-0 text-2xl font-semibold break-all">{e.name}</h1>
          <div className="flex flex-wrap gap-2">
            {canOpenSubmit && (
              <Button onClick={() => setSubmitting(true)}>
                <Send aria-hidden="true" />
                Gửi duyệt
              </Button>
            )}
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
        <p className="text-sm text-muted-foreground">
          {e.owner.full_name} · {e.model.name} · {e.slice.name} ({e.slice.size} ảnh) ·{' '}
          {e.compute_target.name} · {timeText(e)}
        </p>
      </header>
      {banner && (
        <p
          role="status"
          className="flex items-center gap-2 rounded-lg bg-muted px-3 py-2 text-sm font-medium"
          data-testid="dai-khoa"
        >
          <Lock aria-hidden="true" className="size-4 shrink-0" />
          {banner}
        </p>
      )}
      {cancel.isError && <FormAlert>{errorMessage(cancel.error)}</FormAlert>}
      <div
        role="tablist"
        aria-label="Chi tiết experiment"
        className="-mx-4 flex gap-1 overflow-x-auto px-4"
      >
        {tabs.map(([key, label]) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={tab === key}
            onClick={() => setParams(key === 'overview' ? {} : { tab: key }, { replace: true })}
            className={cn(
              'min-h-11 shrink-0 rounded-lg px-3 text-sm font-medium whitespace-nowrap',
              tab === key
                ? 'bg-primary text-primary-foreground'
                : 'text-muted-foreground hover:bg-muted',
            )}
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
            <ExperimentStatusSummary experiment={e} />
            <ProgressBar progress={e.progress} />
            {e.status === 'queued' && e.queue_position !== null && (
              <p className="text-sm">
                Đang chờ trong hàng đợi của {e.compute_target.name}: vị trí {e.queue_position}.
              </p>
            )}
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
