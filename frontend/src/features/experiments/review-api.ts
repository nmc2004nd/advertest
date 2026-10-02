/**
 * Gửi duyệt và bình luận của engineer (requirements.md Phase 8, Frontend engineer; plan task 25,
 * 26). Gửi duyệt thành công trả `ExperimentDetail` mới (đã khóa).
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiGet, apiSend } from '@/api/client'
import type {
  ExperimentDetail,
  ReviewComment,
  ReviewCommentCreate,
  SubmitForReview,
} from '@/contracts/api'

import { EXPERIMENTS_KEY, experimentKey } from './api'

export const commentsKey = (id: string) => [...experimentKey(id), 'comments'] as const

export function useSubmitForReview(id: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: SubmitForReview) =>
      apiSend<ExperimentDetail>('POST', `/experiments/${id}/submit`, body),
    onSuccess: async (detail) => {
      queryClient.setQueryData(experimentKey(id), detail)
      await queryClient.invalidateQueries({ queryKey: EXPERIMENTS_KEY })
    },
  })
}

export function useComments(id: string, enabled = true) {
  return useQuery({
    queryKey: commentsKey(id),
    queryFn: () => apiGet<ReviewComment[]>(`/experiments/${id}/comments`),
    enabled,
  })
}

export function useAddComment(id: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: ReviewCommentCreate) =>
      apiSend<ReviewComment>('POST', `/experiments/${id}/comments`, body),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: commentsKey(id) })
      await queryClient.invalidateQueries({ queryKey: experimentKey(id) })
    },
  })
}
