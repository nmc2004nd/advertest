import { useQuery } from '@tanstack/react-query'

import { apiGet } from '@/api/client'
import { PENDING_COUNT_LIMIT, PENDING_USERS_QUERY_KEY } from '@/auth/pending-count'
import { can } from '@/auth/permissions'
import { useMe } from '@/auth/useMe'
import type { ExperimentPage, ProtocolSummary, ReportView } from '@/contracts/api'
import type { UserAdminPage } from '@/contracts/schemas'
import { EXPERIMENTS_KEY } from '@/features/experiments/api'
import { REPORTS_KEY } from '@/features/reports/api'
import { useReviewQueue } from '@/features/reviews/api'

import { buildStages, type FlowData, nextAction } from './flow'

/** Số liệu của thanh quy trình; chỉ gọi API mà người dùng có quyền (không gây 403). */
export function useFlow() {
  const { data: me } = useMe()
  const admin = can(me, 'user.manage')
  const reviewer = can(me, 'review.decide')

  const pending = useQuery({
    queryKey: PENDING_USERS_QUERY_KEY,
    queryFn: () =>
      apiGet<UserAdminPage>(`/admin/users?status=pending&limit=${PENDING_COUNT_LIMIT}`),
    enabled: admin,
  })
  const protocols = useQuery({
    queryKey: ['protocols', 'flow'],
    queryFn: () => apiGet<ProtocolSummary[]>('/protocols'),
    enabled: can(me, 'protocol.read'),
  })
  const experiments = useQuery({
    queryKey: [...EXPERIMENTS_KEY, 'flow'],
    queryFn: () => apiGet<ExperimentPage>('/experiments?owner=all&limit=50'),
    enabled: can(me, 'experiment.read'),
    refetchInterval: (query) =>
      query.state.data?.items.some((e) => e.status === 'queued' || e.status === 'running')
        ? 5000
        : false,
  })
  const reports = useQuery({
    queryKey: [...REPORTS_KEY, 'flow'],
    queryFn: () => apiGet<ReportView[]>('/reports'),
    enabled: can(me, 'report.read'),
  })
  // Hook luôn được gọi (quy tắc của React); khi không phải reviewer thì bỏ qua kết quả.
  const waiting = useReviewQueue('waiting', 'submitted_at', reviewer)
  const mine = useReviewQueue('mine', 'submitted_at', reviewer)

  const data: FlowData = {
    pendingUsers: admin && pending.data ? pending.data.items.length : null,
    activeProtocols: protocols.data
      ? protocols.data.filter((p) => p.status === 'active').length
      : null,
    experiments: experiments.data?.items ?? null,
    waitingReviews: reviewer && waiting.data ? waiting.data.length : null,
    myReviews: reviewer && mine.data ? mine.data.length : null,
    readyReports: reports.data ? reports.data.filter((r) => r.status === 'ready').length : null,
  }
  const stages = me ? buildStages(me, data) : []
  const loading = experiments.isPending && can(me, 'experiment.read')
  return { me, stages, next: nextAction(stages), loading, experiments: data.experiments ?? [] }
}
