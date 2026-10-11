import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowUpRight, ChevronLeft, Copy } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'

import { apiGet, apiSend } from '@/api/client'
import { errorMessage } from '@/api/messages'
import { can } from '@/auth/permissions'
import { useMe } from '@/auth/useMe'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { FormAlert } from '@/components/FormAlert'
import { LoadError } from '@/components/LoadError'
import { PageLoading } from '@/components/PageLoading'
import { Person } from '@/components/Avatar'
import { StatusBadge } from '@/components/status/StatusBadge'
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
import { Lifecycle } from './Lifecycle'
import { lifecycle } from './lifecycle'
import { OverviewSection } from './OverviewSection'
import { canPromote, PROMOTE_LABEL } from './results'
import { PromoteDialog } from './PromoteDialog'
import { ProgressBar } from './ProgressBar'
import { nextStep } from './next-step'
import { NextStepPanel } from './NextStep'
import { ReportTab } from './ReportTab'
import { ReviewTab } from './ReviewTab'
import { SubmitDialog } from './SubmitDialog'
import { CostTab, FailureCasesTab, ReproTab, ResultsTab, RunsTable } from './tabs'

// Phase R3: 5 tab; Review và Report luôn hiện (trạng thái trống khi chưa có dữ liệu).
const TABS = [
  ['overview', 'Tổng quan'],
  ['results', 'Kết quả'],
  ['cases', 'Failure case'],
  ['review', 'Review'],
  ['report', 'Report'],
] as const

type Tab = (typeof TABS)[number][0]

/** Tab Chi phí và Tái lập cũ: nay là section cuối Tổng quan; `?tab=` cũ mở section đó. */
const LEGACY_SECTIONS = ['cost', 'repro'] as const
type LegacySection = (typeof LEGACY_SECTIONS)[number]

function legacySection(tab: string | null): LegacySection | null {
  return LEGACY_SECTIONS.find((key) => key === tab) ?? null
}

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

/** Link "Nâng từ <tên nguồn>" khi experiment được tạo qua nâng lên chính thức (Phase R3). */
function PromotedFrom({ id }: { id: string }) {
  const source = useQuery({
    queryKey: experimentKey(id),
    queryFn: () => apiGet<ExperimentDetail>(`/experiments/${id}`),
  })
  return (
    <Link
      to={`/experiments/${id}`}
      className="inline-flex min-h-9 items-center gap-1 text-sm font-semibold text-cta underline-offset-4 hover:underline"
    >
      <ArrowUpRight className="size-4" aria-hidden="true" />
      Nâng từ {source.data?.name ?? 'experiment Khám phá nguồn'}
    </Link>
  )
}

/** Chi tiết experiment (requirements.md Phase 5, Frontend: danh sách và chi tiết); Phase 8 thêm gửi
 * duyệt, dải "Đã khóa", tab Review và "Nhân bản để sửa"; Phase R3: thanh vòng đời, nhãn mode, 5 tab
 * (Chi phí và Tái lập thành section của Tổng quan), tab Review và Report luôn hiện. */
export function ExperimentDetailPage() {
  const { id = '' } = useParams()
  const [params, setParams] = useSearchParams()
  // `?tab=cost|repro` cũ: nhớ section cần mở rồi đưa URL về Tổng quan.
  const [section] = useState(() => legacySection(params.get('tab')))
  useEffect(() => {
    if (legacySection(params.get('tab'))) setParams({}, { replace: true })
  }, [params, setParams])
  const tab: Tab = TABS.some(([key]) => key === params.get('tab'))
    ? (params.get('tab') as Tab)
    : 'overview'
  const { data: me } = useMe()
  const experiment = useExperiment(id)
  const runs = useExperimentRuns(id, experiment.data?.status)
  const cancel = useCancel(id)
  const [confirming, setConfirming] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [promoting, setPromoting] = useState(false)

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
  const fixClone = e.status === 'changes_requested'
  const cloneLink = can(me, 'experiment.create') &&
    (e.status === 'changes_requested' || e.status === 'cancelled') && (
      <Button asChild variant="outline">
        <Link to={`/experiments/new?clone=${e.id}`}>
          <Copy aria-hidden="true" />
          {fixClone ? 'Nhân bản để sửa' : 'Nhân bản'}
        </Link>
      </Button>
    )
  // Phase R3: nâng experiment Khám phá đã kết thúc lên chính thức (nút dưới insight của tab Kết quả).
  const promotable = can(me, 'experiment.create') && canPromote(e)
  const promoteButton = promotable && (
    <div className="flex flex-wrap items-center gap-3">
      <Button onClick={() => setPromoting(true)}>
        <ArrowUpRight aria-hidden="true" />
        {PROMOTE_LABEL}
      </Button>
      <p className="text-sm text-muted-foreground">
        Tạo experiment Chính thức theo protocol để gửi duyệt; kết quả Khám phá không được chép sang.
      </p>
    </div>
  )
  const submitButton = canOpenSubmit && (
    <Button onClick={() => setSubmitting(true)}>Gửi duyệt</Button>
  )

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
            <div className="flex flex-wrap items-center gap-2">
              <span data-testid="experiment-mode" className="inline-flex">
                <StatusBadge kind="mode" status={e.mode} />
              </span>
              <ExperimentStatusSummary experiment={e} />
            </div>
            {e.promoted_from && <PromotedFrom id={e.promoted_from} />}
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
        <Lifecycle steps={lifecycle(e)} />
      </header>
      <NextStepPanel experiment={e} view={step} onSubmit={() => setSubmitting(true)} />
      {cancel.isError && <FormAlert>{errorMessage(cancel.error)}</FormAlert>}
      <div role="tablist" aria-label="Chi tiết experiment" className="seg self-start">
        {TABS.map(([key, label]) => (
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
        aria-label={TABS.find(([key]) => key === tab)?.[1]}
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
            <OverviewSection
              title="Chi phí"
              defaultOpen={section === 'cost'}
              scrollTo={section === 'cost' && !runs.isPending}
            >
              <CostTab experiment={e} runs={runList} />
            </OverviewSection>
            <OverviewSection
              title="Tái lập"
              defaultOpen={section === 'repro'}
              scrollTo={section === 'repro' && !runs.isPending}
            >
              <ReproTab runs={runList} />
            </OverviewSection>
          </div>
        )}
        {tab === 'results' && (
          <ResultsTab experiment={e} runs={runList} action={promoteButton || undefined} />
        )}
        {tab === 'cases' && <FailureCasesTab runs={runList} />}
        {tab === 'review' && (
          <ReviewTab experiment={e} runs={runList} action={submitButton || cloneLink} />
        )}
        {tab === 'report' && <ReportTab experiment={e} action={cloneLink} />}
      </section>
      {canOpenSubmit && (
        <SubmitDialog
          experiment={e}
          runs={runList}
          open={submitting}
          onOpenChange={setSubmitting}
        />
      )}
      {promotable && <PromoteDialog experiment={e} open={promoting} onOpenChange={setPromoting} />}
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
