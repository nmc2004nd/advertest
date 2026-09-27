import { useQuery } from '@tanstack/react-query'

import type { HealthResponse, RunResultOutput as RunResult } from '@/contracts/api'

import { apiGet } from './client'

/** tech-stack.md mục 5: polling 2 giây, tắt khi tab ẩn (mặc định của TanStack Query). */
export const POLL_INTERVAL_MS = 2000

export function useHealth() {
  return useQuery({ queryKey: ['health'], queryFn: () => apiGet<HealthResponse>('/health') })
}

export function useRun(runId: string) {
  return useQuery({
    queryKey: ['runs', runId],
    queryFn: () => apiGet<RunResult>(`/runs/${runId}`),
    refetchInterval: POLL_INTERVAL_MS,
  })
}
