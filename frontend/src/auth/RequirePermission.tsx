import type { ReactNode } from 'react'
import { Navigate } from 'react-router'

import { ApiError } from '@/api/client'
import { LoadError } from '@/components/LoadError'
import { PageLoading } from '@/components/PageLoading'

import { can, type Requirement } from './permissions'
import { useMe } from './useMe'

/**
 * Chỉ hiện `children` khi người dùng có quyền; thiếu quyền → `/forbidden`. Chưa đăng nhập: lỗi
 * 401 của `/auth/me` được xử lý toàn cục (chuyển về `/login`). Chỉ để giao diện gọn: backend chặn.
 */
export function RequirePermission({
  requirement,
  children,
}: {
  requirement: Requirement
  children: ReactNode
}) {
  const { data: me, isPending, error, refetch, isFetching } = useMe()
  if (isPending) return <PageLoading />
  if (!me) {
    // 401: đã được chuyển về /login ở tầng xử lý lỗi toàn cục. Lỗi khác (500, mất mạng): báo lỗi.
    if (error instanceof ApiError && error.status === 401) return null
    return <LoadError onRetry={() => void refetch()} retrying={isFetching} />
  }
  if (!can(me, requirement)) return <Navigate to="/forbidden" replace />
  return children
}
