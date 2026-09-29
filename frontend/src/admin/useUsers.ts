import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query'

import { apiGet, apiSend } from '@/api/client'
import { ME_QUERY_KEY } from '@/auth/useMe'
import type { UserAdminPage, UserStatus } from '@/contracts/schemas'

/** Mọi khóa cache của trang quản trị người dùng bắt đầu bằng đây (gồm số chờ duyệt ở /home). */
export const ADMIN_USERS_KEY = ['admin', 'users'] as const
export const AUDIT_KEY = ['audit'] as const
const PAGE_SIZE = 50

export function useUserList(status: UserStatus | null) {
  return useInfiniteQuery({
    queryKey: [...ADMIN_USERS_KEY, 'list', status ?? 'all'],
    queryFn: ({ pageParam }) => {
      const params = new URLSearchParams({ limit: String(PAGE_SIZE) })
      if (status) params.set('status', status)
      if (pageParam) params.set('cursor', pageParam)
      return apiGet<UserAdminPage>(`/admin/users?${params}`)
    },
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
  })
}

/**
 * Thao tác quản trị: xong thì làm mới danh sách, số chờ duyệt (`/home`), audit log, và `me`
 * (admin có thể vừa đổi role của chính mình).
 */
export function useAdminMutation<Body, Result>(
  method: 'POST' | 'PUT',
  path: (userId: string) => string,
) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ userId, body }: { userId: string; body?: Body }) =>
      apiSend<Result>(method, path(userId), body),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ADMIN_USERS_KEY }),
        queryClient.invalidateQueries({ queryKey: AUDIT_KEY }),
        queryClient.invalidateQueries({ queryKey: ME_QUERY_KEY }),
      ])
    },
  })
}
