import type { ReactNode } from 'react'
import { Navigate } from 'react-router'

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
  const { data: me, isPending } = useMe()
  if (isPending) return <PageLoading />
  if (!me) return null
  if (!can(me, requirement)) return <Navigate to="/forbidden" replace />
  return children
}
