import { useQuery } from '@tanstack/react-query'

import type { HealthResponse, RunStatus, RunView } from '@/contracts/api'

import { apiGet } from './client'

/** tech-stack.md mục 5: polling 2 giây, tắt khi tab ẩn (mặc định của TanStack Query). */
export const POLL_INTERVAL_MS = 2000

const FINISHED_RUN: readonly RunStatus[] = [
  'completed',
  'failed',
  'skipped',
  'stopped_limit',
  'cancelled',
]

export function useHealth() {
  return useQuery({ queryKey: ['health'], queryFn: () => apiGet<HealthResponse>('/health') })
}

/** Run theo id; dừng polling khi run đã kết thúc (roadmap: từ Phase 0). */
export function useRun(runId: string) {
  return useQuery({
    queryKey: ['runs', runId],
    queryFn: () => apiGet<RunView>(`/runs/${runId}`),
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status !== undefined && FINISHED_RUN.includes(status) ? false : POLL_INTERVAL_MS
    },
  })
}
