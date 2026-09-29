import { useInfiniteQuery } from '@tanstack/react-query'

import { apiGet } from '@/api/client'
import type { AuditLogPage } from '@/contracts/schemas'

import { dayRangeToUtc } from './format'
import { AUDIT_KEY } from './useUsers'

/** Bộ lọc trên giao diện; ngày theo giờ máy người dùng (`YYYY-MM-DD`), rỗng là không lọc. */
export interface AuditFilters {
  actorId: string
  action: string
  entityType: string
  from: string
  to: string
}

export const EMPTY_FILTERS: AuditFilters = {
  actorId: '',
  action: '',
  entityType: '',
  from: '',
  to: '',
}

const PAGE_SIZE = 50

/** Tham số query của `GET /audit-log` (requirements.md Phase 4, chi tiết phản hồi). */
export function auditParams(filters: AuditFilters, cursor: string | null): URLSearchParams {
  const params = new URLSearchParams({ limit: String(PAGE_SIZE) })
  if (filters.actorId) params.set('actor_id', filters.actorId)
  if (filters.action) params.set('action', filters.action)
  if (filters.entityType.trim()) params.set('entity_type', filters.entityType.trim())
  const { since, until } = dayRangeToUtc(filters.from, filters.to)
  if (since) params.set('since', since)
  if (until) params.set('until', until)
  if (cursor) params.set('cursor', cursor)
  return params
}

export function useAuditLog(filters: AuditFilters) {
  return useInfiniteQuery({
    queryKey: [...AUDIT_KEY, filters],
    queryFn: ({ pageParam }) =>
      apiGet<AuditLogPage>(`/audit-log?${auditParams(filters, pageParam)}`),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
  })
}
