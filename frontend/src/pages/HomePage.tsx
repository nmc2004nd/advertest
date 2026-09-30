import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router'

import { apiGet } from '@/api/client'
import {
  PENDING_COUNT_LIMIT,
  PENDING_USERS_QUERY_KEY,
  pendingCountLabel,
} from '@/auth/pending-count'
import { ROLE_LABELS } from '@/auth/roles'
import { useMe } from '@/auth/useMe'
import type { Role, UserAdminPage } from '@/contracts/schemas'
import { EngineerHome } from '@/features/experiments/EngineerHome'

/** "Việc của tôi" theo từng role người dùng có (requirements.md Phase 4, mục Điều hướng). */
export function HomePage() {
  const { data: me } = useMe()
  if (!me) return null
  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6 p-4 md:p-6">
      <h1 className="text-2xl font-semibold">Xin chào, {me.full_name}</h1>
      {me.roles.length === 0 ? (
        <p className="text-muted-foreground">Tài khoản chưa được gán vai trò nào.</p>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {me.roles.map((role) => (
            <RoleBlock key={role} role={role} />
          ))}
        </div>
      )}
    </div>
  )
}

function RoleBlock({ role }: { role: Role }) {
  return (
    <section className="flex flex-col gap-2 rounded-xl border border-border p-4">
      <h2 className="font-semibold">{ROLE_LABELS[role]}</h2>
      {role === 'admin' ? (
        <PendingUsers />
      ) : role === 'engineer' ? (
        <EngineerHome />
      ) : (
        <p className="text-muted-foreground">Sắp có.</p>
      )}
    </section>
  )
}

function PendingUsers() {
  const { data, isPending, isError } = useQuery({
    queryKey: PENDING_USERS_QUERY_KEY,
    queryFn: () =>
      apiGet<UserAdminPage>(`/admin/users?status=pending&limit=${PENDING_COUNT_LIMIT}`),
  })
  if (isPending) return <p className="text-muted-foreground">Đang tải…</p>
  if (isError) return <p className="text-destructive">Không tải được số tài khoản chờ duyệt.</p>
  return (
    <Link
      to="/admin/users"
      className="inline-flex min-h-11 items-baseline gap-2 rounded-lg focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
    >
      <span className="text-3xl font-semibold" data-testid="so-cho-duyet">
        {pendingCountLabel(data)}
      </span>
      <span className="text-muted-foreground">tài khoản chờ duyệt</span>
    </Link>
  )
}
