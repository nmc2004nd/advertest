import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiGet, apiSend } from '@/api/client'
import { POLL_INTERVAL_MS } from '@/api/queries'
import type {
  AttackAdapterInfo,
  AttackSpecAdminPage,
  AttackSpecAdminView,
  AttackSpecCreate,
  AttackSpecMetadata,
  AttackSpecView,
  AuditLogPage,
} from '@/contracts/api'

import { ATTACK_CATALOG_KEY } from './useAttackCatalog'

const ALL_SPECS_KEY = [...ATTACK_CATALOG_KEY, 'all'] as const
const PAGE_LIMIT = 100

/**
 * Mọi spec của `GET /admin/attack-specs` (duyệt hết các trang): form cần version lớn nhất của mỗi
 * tên, trang chi tiết tìm spec theo id (API không có endpoint chi tiết spec).
 */
export async function fetchAllAdminSpecs(): Promise<AttackSpecAdminView[]> {
  const items: AttackSpecAdminView[] = []
  let cursor: string | null = null
  do {
    const params = new URLSearchParams({ limit: String(PAGE_LIMIT) })
    if (cursor) params.set('cursor', cursor)
    const page: AttackSpecAdminPage = await apiGet<AttackSpecAdminPage>(
      `/admin/attack-specs?${params}`,
    )
    items.push(...page.items)
    cursor = page.next_cursor
  } while (cursor)
  return items
}

export function useAllAdminSpecs() {
  return useQuery({ queryKey: ALL_SPECS_KEY, queryFn: fetchAllAdminSpecs })
}

/** Một spec theo id; đang `checking` thì tự cập nhật mỗi 2 giây (tech-stack.md mục 5). */
export function useAdminSpec(id: string) {
  const query = useQuery({
    queryKey: ALL_SPECS_KEY,
    queryFn: fetchAllAdminSpecs,
    refetchInterval: (q) =>
      q.state.data?.find((s) => s.id === id)?.status === 'checking' ? POLL_INTERVAL_MS : false,
  })
  return { ...query, spec: query.data?.find((s) => s.id === id) }
}

export function useAttackAdapters() {
  return useQuery({
    queryKey: ['attack-adapters'],
    queryFn: () => apiGet<AttackAdapterInfo[]>('/attack-adapters'),
    staleTime: Infinity,
  })
}

/** Lý do từ chối gần nhất của spec: chỉ nằm trong audit log (`attack_spec.rejected`). */
export function useRejectReason(specId: string, enabled: boolean) {
  return useQuery({
    queryKey: ['audit', 'attack_spec.rejected', specId],
    enabled,
    queryFn: async () => {
      const params = new URLSearchParams({
        entity_type: 'attack_spec',
        entity_id: specId,
        action: 'attack_spec.rejected',
        limit: '1',
      })
      const page = await apiGet<AuditLogPage>(`/audit-log?${params}`)
      const reason = page.items[0]?.after?.reason
      return typeof reason === 'string' ? reason : null
    },
  })
}

/** Spec chờ duyệt (`attack_catalog.approve`); cùng khóa với việc cần làm ở trang chủ. */
export function usePendingSpecs() {
  return useQuery({
    queryKey: ['attack-specs', 'pending'],
    queryFn: () => apiGet<AttackSpecAdminView[]>('/attack-specs/pending'),
  })
}

/** Spec `active` (`attack_catalog.read`): so khác biệt với version đang dùng. */
export function useActiveSpecs() {
  return useQuery({
    queryKey: ['attack-specs'],
    queryFn: () => apiGet<AttackSpecView[]>('/attack-specs'),
  })
}

function useSpecMutation<Vars>(send: (vars: Vars) => Promise<AttackSpecAdminView>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: send,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ATTACK_CATALOG_KEY }),
        queryClient.invalidateQueries({ queryKey: ['attack-specs'] }),
        queryClient.invalidateQueries({ queryKey: ['audit'] }),
      ])
    },
  })
}

export const useCreateSpec = () =>
  useSpecMutation((body: AttackSpecCreate) =>
    apiSend<AttackSpecAdminView>('POST', '/admin/attack-specs', body),
  )

export const useRecheckSpec = () =>
  useSpecMutation((id: string) =>
    apiSend<AttackSpecAdminView>('POST', `/admin/attack-specs/${id}/check`),
  )

export const useUpdateSpecMetadata = () =>
  useSpecMutation(({ id, metadata }: { id: string; metadata: AttackSpecMetadata }) =>
    apiSend<AttackSpecAdminView>('PATCH', `/admin/attack-specs/${id}/metadata`, metadata),
  )

export const useApproveSpec = () =>
  useSpecMutation((id: string) =>
    apiSend<AttackSpecAdminView>('POST', `/attack-specs/${id}/approve`),
  )

export const useRejectSpec = () =>
  useSpecMutation(({ id, reason }: { id: string; reason: string }) =>
    apiSend<AttackSpecAdminView>('POST', `/attack-specs/${id}/reject`, { reason }),
  )
