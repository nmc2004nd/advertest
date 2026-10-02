/**
 * Report (requirements.md Phase 8, mục Report và Frontend; plan task 32-33): danh sách, chi tiết
 * (snapshot đã lưu), URL tải tạm thời, sinh lại, thông tin xác minh công khai.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiGet, apiSend } from '@/api/client'
import type { ReportDetail, ReportDownload, ReportView, VerifyInfo } from '@/contracts/api'
import { EXPERIMENTS_KEY } from '@/features/experiments/api'

export const REPORTS_KEY = ['reports'] as const
export const reportKey = (id: string) => [...REPORTS_KEY, id] as const
/** Report đang sinh: tải lại tới khi `ready` hoặc `failed`. */
export const GENERATING_POLL_MS = 3000

export function useReports() {
  return useQuery({
    queryKey: REPORTS_KEY,
    queryFn: () => apiGet<ReportView[]>('/reports'),
    refetchInterval: (query) =>
      query.state.data?.some((r) => r.status === 'generating') ? GENERATING_POLL_MS : false,
  })
}

export function useReport(id: string) {
  return useQuery({
    queryKey: reportKey(id),
    queryFn: () => apiGet<ReportDetail>(`/reports/${id}`),
    refetchInterval: (query) =>
      query.state.data?.report.status === 'generating' ? GENERATING_POLL_MS : false,
  })
}

/** Xin URL tải (mỗi lần xin ghi `report.downloaded`), rồi mở URL đó. */
export function useDownloadReport(id: string) {
  return useMutation({
    mutationFn: (format: ReportDownload['format']) =>
      apiGet<ReportDownload>(`/reports/${id}/download?format=${format}`),
  })
}

export function useRegenerateReport(id: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => apiSend<ReportView>('POST', `/reports/${id}/regenerate`),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: REPORTS_KEY })
      await queryClient.invalidateQueries({ queryKey: EXPERIMENTS_KEY })
    },
  })
}

export const verifyKey = (id: string) => ['verify', id] as const

/** Công khai: không cần đăng nhập; chỉ report `ready`, còn lại 404. */
export function useVerifyInfo(id: string) {
  return useQuery({
    queryKey: verifyKey(id),
    queryFn: () => apiGet<VerifyInfo>(`/verify/${id}`),
    retry: false,
  })
}
