/**
 * Hook dữ liệu của experiment, run, failure case (requirements.md Phase 5, API experiment).
 *
 * Polling 2 giây khi experiment còn `queued`/`running`, dừng khi đã ở trạng thái cuối; TanStack
 * Query tự tạm dừng polling khi tab bị ẩn (`refetchIntervalInBackground` mặc định là false).
 */
import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useRef } from 'react'

import { apiGet } from '@/api/client'
import { POLL_INTERVAL_MS } from '@/api/queries'
import type {
  AttackSpec,
  ExperimentDetail,
  ExperimentPage,
  ExperimentStatus,
  FailureCaseView,
  Manifest,
  RunStatus,
  RunView,
} from '@/contracts/api'

/** Experiment còn thay đổi (worker đang hoặc sẽ chạy): cần polling. */
export const ACTIVE_EXPERIMENT: readonly ExperimentStatus[] = ['queued', 'running']
export const ACTIVE_RUN: readonly RunStatus[] = ['queued', 'running']

export function experimentPollInterval(status: ExperimentStatus | undefined): number | false {
  return status === undefined || ACTIVE_EXPERIMENT.includes(status) ? POLL_INTERVAL_MS : false
}

export function runPollInterval(status: RunStatus | undefined): number | false {
  return status === undefined || ACTIVE_RUN.includes(status) ? POLL_INTERVAL_MS : false
}

export const experimentKey = (id: string) => ['experiments', id] as const
export const EXPERIMENTS_KEY = ['experiments'] as const

export function useExperiment(id: string) {
  return useQuery({
    queryKey: experimentKey(id),
    queryFn: () => apiGet<ExperimentDetail>(`/experiments/${id}`),
    refetchInterval: (query) => experimentPollInterval(query.state.data?.status),
  })
}

/** Danh sách run polling theo trạng thái của experiment (không theo từng run). */
export function useExperimentRuns(id: string, status: ExperimentStatus | undefined) {
  return useQuery({
    queryKey: [...experimentKey(id), 'runs'],
    queryFn: () => apiGet<RunView[]>(`/experiments/${id}/runs`),
    refetchInterval: experimentPollInterval(status),
  })
}

export interface ExperimentFilters {
  owner: 'me' | 'all'
  status: ExperimentStatus | ''
  model: string
}

const PAGE_SIZE = 20

export function experimentParams(filters: ExperimentFilters, cursor: string | null) {
  const params = new URLSearchParams({ owner: filters.owner, limit: String(PAGE_SIZE) })
  if (filters.status) params.set('status', filters.status)
  if (filters.model) params.set('model', filters.model)
  if (cursor) params.set('cursor', cursor)
  return params
}

/** Danh sách có "Tải thêm"; polling khi trang đầu còn experiment đang chạy hoặc chờ. */
export function useExperiments(filters: ExperimentFilters) {
  return useInfiniteQuery({
    queryKey: [...EXPERIMENTS_KEY, 'list', filters],
    queryFn: ({ pageParam }) =>
      apiGet<ExperimentPage>(`/experiments?${experimentParams(filters, pageParam)}`),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
    refetchInterval: (query) => {
      const items = query.state.data?.pages.flatMap((page) => page.items) ?? []
      return items.some((e) => ACTIVE_EXPERIMENT.includes(e.status)) ? POLL_INTERVAL_MS : false
    },
  })
}

export function useManifest(runId: string, enabled = true) {
  return useQuery({
    queryKey: ['runs', runId, 'manifest'],
    queryFn: () => apiGet<Manifest>(`/runs/${runId}/manifest`),
    enabled,
    staleTime: Infinity, // manifest không đổi sau khi run xong
  })
}

// ---------------------------------------------------------------- failure case và URL ảnh

/** Xin lại URL trước khi hết hạn một khoảng này (URL sống 10 phút). */
export const URL_REFRESH_MARGIN_MS = 60_000

/**
 * Số mili giây nữa thì phải xin lại URL ảnh (`urls_expire_at` trừ biên an toàn), không âm;
 * `null` khi không có URL (ảnh bị ẩn).
 */
export function msUntilUrlRefresh(
  expiresAt: string | null | undefined,
  now: number,
): number | null {
  if (!expiresAt) return null
  return Math.max(0, Date.parse(expiresAt) - URL_REFRESH_MARGIN_MS - now)
}

/** Tải lại query khi URL ảnh sắp hết hạn (task 22). */
function useRefreshBeforeExpiry(
  queryKey: readonly unknown[],
  expiresAt: string | null | undefined,
): void {
  const client = useQueryClient()
  const key = JSON.stringify(queryKey)
  useEffect(() => {
    const wait = msUntilUrlRefresh(expiresAt, Date.now())
    if (wait === null) return
    const timer = setTimeout(
      () => void client.invalidateQueries({ queryKey: JSON.parse(key) as unknown[] }),
      wait,
    )
    return () => clearTimeout(timer)
  }, [client, key, expiresAt])
}

export const failureCasesKey = (runId: string) => ['runs', runId, 'failure-cases'] as const
export const failureCaseKey = (id: string) => ['failure-cases', id] as const

/** Failure case của một run (chỉ URL thumbnail), `severity_score` giảm dần. */
export function useFailureCases(runId: string, enabled = true) {
  const query = useQuery({
    queryKey: failureCasesKey(runId),
    queryFn: () => apiGet<FailureCaseView[]>(`/runs/${runId}/failure-cases`),
    enabled,
  })
  useRefreshBeforeExpiry(failureCasesKey(runId), query.data?.[0]?.urls_expire_at)
  return query
}

/** Một failure case đủ URL; tự xin lại URL trước khi hết hạn. */
export function useFailureCase(id: string) {
  const query = useQuery({
    queryKey: failureCaseKey(id),
    queryFn: () => apiGet<FailureCaseView>(`/failure-cases/${id}`),
  })
  useRefreshBeforeExpiry(failureCaseKey(id), query.data?.urls_expire_at)
  return query
}

/**
 * Ảnh tải lỗi (thường do URL vừa hết hạn): xin lại case, mỗi bộ URL chỉ thử một lần để không
 * lặp vô hạn khi ảnh thật sự không có (task 22). `urlsKey` thường là `urls_expire_at`.
 */
export function useRetryOnImageError(refetch: () => unknown, urlsKey: string | null | undefined) {
  const tried = useRef<string | null | undefined>(undefined)
  return useCallback(() => {
    if (!urlsKey || tried.current === urlsKey) return
    tried.current = urlsKey
    void refetch()
  }, [refetch, urlsKey])
}

/** URL ảnh của API (`/artifacts/...`) thành URL trình duyệt tải được (qua `/api` khi có). */
export function artifactSrc(url: string | null | undefined): string | null {
  return url ? `${import.meta.env.VITE_API_BASE_URL ?? ''}${url}` : null
}

/** 50 experiment mới nhất của tôi (khối "việc của tôi" trên /home); polling khi có cái đang chạy. */
export function useMyRecentExperiments() {
  return useQuery({
    queryKey: [...EXPERIMENTS_KEY, 'mine-recent'],
    queryFn: () => apiGet<ExperimentPage>('/experiments?owner=me&limit=50'),
    refetchInterval: (query) =>
      query.state.data?.items.some((e) => ACTIVE_EXPERIMENT.includes(e.status))
        ? POLL_INTERVAL_MS
        : false,
  })
}

/** Catalog attack (Phase 7: tên và dải của attack tìm ngưỡng chưa có run). Cùng khóa với wizard. */
export function useAttackCatalog() {
  return useQuery({
    queryKey: ['attack-specs'],
    queryFn: () => apiGet<AttackSpec[]>('/attack-specs'),
  })
}
