/**
 * Dữ liệu của reviewer (requirements.md Phase 8, Frontend reviewer; plan task 27-29): hàng đợi,
 * nhận/trả lại, quyết định, verdict. Mọi thao tác trả `ExperimentDetail` mới hoặc verdict mới;
 * cache của experiment được cập nhật để trang không cần tải lại.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiGet, apiSend } from '@/api/client'
import type {
  CaseVerdictInput,
  CaseVerdictView,
  ExperimentDetail,
  ReviewDecisionInput,
  ReviewQueueFilter,
  ReviewQueueItem,
} from '@/contracts/api'
import { EXPERIMENTS_KEY, experimentKey } from '@/features/experiments/api'

export const REVIEWS_KEY = ['reviews'] as const
export type QueueSort = 'submitted_at' | 'max_drop'

export function useReviewQueue(status: ReviewQueueFilter, sort: QueueSort = 'submitted_at') {
  return useQuery({
    queryKey: [...REVIEWS_KEY, status, sort],
    queryFn: () =>
      apiGet<ReviewQueueItem[]>(`/reviews?${new URLSearchParams({ status, sort }).toString()}`),
  })
}

function useExperimentAction<Body>(id: string, path: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: Body) => apiSend<ExperimentDetail>('POST', path, body),
    onSuccess: async (detail) => {
      queryClient.setQueryData(experimentKey(id), detail)
      await queryClient.invalidateQueries({ queryKey: REVIEWS_KEY })
      await queryClient.invalidateQueries({ queryKey: EXPERIMENTS_KEY })
    },
  })
}

export const useClaim = (id: string) => useExperimentAction<undefined>(id, `/reviews/${id}/claim`)
export const useRelease = (id: string) =>
  useExperimentAction<undefined>(id, `/reviews/${id}/release`)
export const useDecide = (id: string) =>
  useExperimentAction<ReviewDecisionInput>(id, `/reviews/${id}/decision`)

export const verdictsKey = (caseId: string) => ['failure-cases', caseId, 'verdicts'] as const

/** Mọi version verdict của case, mới nhất trước. */
export function useVerdicts(caseId: string) {
  return useQuery({
    queryKey: verdictsKey(caseId),
    queryFn: () => apiGet<CaseVerdictView[]>(`/failure-cases/${caseId}/verdicts`),
  })
}

export function useAddVerdict(experimentId: string, caseId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: CaseVerdictInput) =>
      apiSend<CaseVerdictView>('POST', `/reviews/${experimentId}/cases/${caseId}/verdicts`, body),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: verdictsKey(caseId) })
      // Tiến độ case bắt buộc và checklist nằm trong ExperimentDetail.review.
      await queryClient.invalidateQueries({ queryKey: experimentKey(experimentId) })
      await queryClient.invalidateQueries({ queryKey: REVIEWS_KEY })
    },
  })
}
