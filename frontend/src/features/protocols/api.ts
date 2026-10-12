/**
 * Protocol (requirements.md Phase 8, Frontend reviewer; plan task 30): danh sách gồm cả bản đã
 * ngừng dùng, tạo, tạo version mới, ngừng dùng. Key `['protocols']` dùng chung với wizard nên
 * wizard thấy ngay protocol mới.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiGet, apiSend } from '@/api/client'
import type {
  ProtocolCreate,
  ProtocolSummary,
  ProtocolTemplate,
  ProtocolVersionCreate,
  ProtocolView,
} from '@/contracts/api'

const PROTOCOLS_KEY = ['protocols'] as const

export function useAllProtocols() {
  return useQuery({
    queryKey: [...PROTOCOLS_KEY, 'all'],
    queryFn: () => apiGet<ProtocolSummary[]>('/protocols?include_retired=true'),
  })
}

/** Mẫu protocol (Phase R2, seed): chỉ điền sẵn form, không tự tạo protocol. */
export const useProtocolTemplates = () =>
  useQuery({
    queryKey: ['protocol-templates'],
    queryFn: () => apiGet<ProtocolTemplate[]>('/protocol-templates'),
    staleTime: Infinity,
  })

/** Bản nháp `ProtocolCreate` của một mẫu: spec active, level và tiêu chí gợi ý. */
export const fetchTemplateDraft = (key: ProtocolTemplate['key']) =>
  apiGet<ProtocolCreate>(`/protocol-templates/${key}/draft`)

function useProtocolMutation<Body>(send: (body: Body) => Promise<ProtocolView>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: send,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: PROTOCOLS_KEY })
    },
  })
}

export const useCreateProtocol = () =>
  useProtocolMutation((body: ProtocolCreate) => apiSend<ProtocolView>('POST', '/protocols', body))

export const useNewVersion = (id: string) =>
  useProtocolMutation((body: ProtocolVersionCreate) =>
    apiSend<ProtocolView>('POST', `/protocols/${id}/versions`, body),
  )

export const useRetireProtocol = () =>
  useProtocolMutation((id: string) => apiSend<ProtocolView>('POST', `/protocols/${id}/retire`))
