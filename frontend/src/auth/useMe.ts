import { useQuery } from '@tanstack/react-query'

import { apiGet } from '@/api/client'
import type { Me } from '@/contracts/schemas'

import { can, type Requirement } from './permissions'

export const ME_QUERY_KEY = ['auth', 'me'] as const

/** Người dùng đang đăng nhập (`GET /auth/me`); lỗi 401 được xử lý toàn cục. */
export function useMe() {
  return useQuery({
    queryKey: ME_QUERY_KEY,
    queryFn: () => apiGet<Me>('/auth/me'),
    retry: false,
    staleTime: 30_000,
  })
}

/** `can` với người dùng hiện tại; false khi chưa tải xong. */
export function useCan(requirement: Requirement): boolean {
  const { data } = useMe()
  return can(data, requirement)
}
