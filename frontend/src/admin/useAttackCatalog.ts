import { useInfiniteQuery } from '@tanstack/react-query'

import { apiGet } from '@/api/client'
import type { AttackSpecAdminPage } from '@/contracts/api'

const PAGE_SIZE = 50

export const ATTACK_CATALOG_KEY = ['admin', 'attack-specs'] as const

/** `GET /admin/attack-specs`: mọi spec và version, kể cả spec đã tắt (Phase 6, task 35). */
export function useAttackCatalog() {
  return useInfiniteQuery({
    queryKey: ATTACK_CATALOG_KEY,
    queryFn: ({ pageParam }) => {
      const params = new URLSearchParams({ limit: String(PAGE_SIZE) })
      if (pageParam) params.set('cursor', pageParam)
      return apiGet<AttackSpecAdminPage>(`/admin/attack-specs?${params}`)
    },
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
  })
}
