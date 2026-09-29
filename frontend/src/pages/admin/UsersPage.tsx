import { createColumnHelper, tableFeatures, useTable } from '@tanstack/react-table'
import { useMemo, useState } from 'react'

import { formatDateTime, USER_STATUS_LABELS } from '@/admin/format'
import { ACTION_LABELS, actionsFor, type UserAction } from '@/admin/user-actions'
import {
  ApproveDialog,
  DisableDialog,
  RejectDialog,
  ResetLinkDialog,
  RolesDialog,
} from '@/admin/UserDialogs'
import { useAdminMutation, useUserList } from '@/admin/useUsers'
import { errorMessage } from '@/api/messages'
import { ROLE_LABELS } from '@/auth/roles'
import { useMe } from '@/auth/useMe'
import { FormAlert } from '@/components/FormAlert'
import { LoadError } from '@/components/LoadError'
import { PageLoading } from '@/components/PageLoading'
import { Button } from '@/components/ui/button'
import type { UserAdminView } from '@/contracts/schemas'

type Tab = 'pending' | 'all'
type OpenDialog = { action: Exclude<UserAction, 'enable'>; user: UserAdminView } | null

const TABS: readonly (readonly [Tab, string])[] = [
  ['pending', 'Chờ duyệt'],
  ['all', 'Tất cả'],
]

export function UsersPage() {
  const [tab, setTab] = useState<Tab>('pending')
  const [dialog, setDialog] = useState<OpenDialog>(null)
  const list = useUserList(tab === 'pending' ? 'pending' : null)
  const enable = useAdminMutation<undefined, UserAdminView>(
    'POST',
    (id) => `/admin/users/${id}/enable`,
  )
  const users = list.data?.pages.flatMap((page) => page.items) ?? []
  const onAction = (action: UserAction, user: UserAdminView) =>
    action === 'enable' ? enable.mutate({ userId: user.id }) : setDialog({ action, user })

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-4 p-4 md:p-6">
      <h1 className="text-2xl font-semibold">Người dùng</h1>
      <div role="tablist" aria-label="Lọc người dùng" className="flex gap-2">
        {TABS.map(([value, label]) => (
          <Button
            key={value}
            role="tab"
            aria-selected={tab === value}
            variant={tab === value ? 'default' : 'outline'}
            onClick={() => setTab(value)}
          >
            {label}
          </Button>
        ))}
      </div>
      {enable.isError && <FormAlert>{errorMessage(enable.error)}</FormAlert>}
      {list.isPending ? (
        <PageLoading />
      ) : list.isError ? (
        <LoadError onRetry={() => void list.refetch()} retrying={list.isFetching} />
      ) : users.length === 0 ? (
        <p className="text-muted-foreground">
          {tab === 'pending' ? 'Không có yêu cầu nào chờ duyệt.' : 'Chưa có người dùng nào.'}
        </p>
      ) : (
        <>
          <UserTable users={users} onAction={onAction} />
          <UserCards users={users} onAction={onAction} />
          {list.hasNextPage && (
            <Button
              variant="outline"
              className="self-center"
              disabled={list.isFetchingNextPage}
              onClick={() => void list.fetchNextPage()}
            >
              {list.isFetchingNextPage ? 'Đang tải…' : 'Tải thêm'}
            </Button>
          )}
        </>
      )}
      {dialog && <UserDialog {...dialog} onClose={() => setDialog(null)} />}
    </div>
  )
}

function UserDialog({ action, user, onClose }: NonNullable<OpenDialog> & { onClose: () => void }) {
  switch (action) {
    case 'approve':
      return <ApproveDialog user={user} onClose={onClose} />
    case 'reject':
      return <RejectDialog user={user} onClose={onClose} />
    case 'roles':
      return <RolesDialog user={user} onClose={onClose} />
    case 'disable':
      return <DisableDialog user={user} onClose={onClose} />
    case 'reset-link':
      return <ResetLinkDialog user={user} onClose={onClose} />
  }
}

interface ListProps {
  users: UserAdminView[]
  onAction: (action: UserAction, user: UserAdminView) => void
}

const PRIMARY: readonly UserAction[] = ['approve', 'enable']
const DESTRUCTIVE: readonly UserAction[] = ['reject', 'disable']

function Actions({ user, onAction }: { user: UserAdminView } & Pick<ListProps, 'onAction'>) {
  const { data: me } = useMe()
  const actions = actionsFor(user, me?.id)
  if (actions.length === 0) return <span className="text-sm text-muted-foreground">—</span>
  return (
    <div className="flex flex-wrap gap-2">
      {actions.map((action) => (
        <Button
          key={action}
          variant={PRIMARY.includes(action) ? 'default' : 'outline'}
          className={DESTRUCTIVE.includes(action) ? 'text-destructive' : undefined}
          onClick={() => onAction(action, user)}
          aria-label={`${ACTION_LABELS[action]}: ${user.full_name}`}
        >
          {ACTION_LABELS[action]}
        </Button>
      ))}
    </div>
  )
}

function roles(user: UserAdminView): string {
  return user.roles.map((role) => ROLE_LABELS[role]).join(', ') || '—'
}

function requestInfo(user: UserAdminView): string {
  const role = user.requested_role ? ROLE_LABELS[user.requested_role] : '—'
  return user.request_reason ? `${role}: ${user.request_reason}` : role
}

const features = tableFeatures({})
const column = createColumnHelper<typeof features, UserAdminView>()

/** Bảng (TanStack Table v9): chỉ hiện từ 1280px (desktop). */
function UserTable({ users, onAction }: ListProps) {
  const columns = useMemo(
    () =>
      column.columns([
        column.accessor('full_name', {
          header: 'Người dùng',
          cell: ({ row }) => (
            <div className="flex flex-col">
              <span className="font-medium">{row.original.full_name}</span>
              <span className="text-muted-foreground">{row.original.email}</span>
              {row.original.organization && (
                <span className="text-muted-foreground">{row.original.organization}</span>
              )}
            </div>
          ),
        }),
        column.accessor('status', {
          header: 'Trạng thái',
          cell: ({ row }) => (
            <div className="flex flex-col">
              <span>{USER_STATUS_LABELS[row.original.status]}</span>
              {row.original.reject_reason && (
                <span className="text-muted-foreground">Lý do: {row.original.reject_reason}</span>
              )}
            </div>
          ),
        }),
        column.display({ id: 'roles', header: 'Vai trò', cell: ({ row }) => roles(row.original) }),
        column.display({
          id: 'request',
          header: 'Yêu cầu',
          cell: ({ row }) => <span className="line-clamp-3">{requestInfo(row.original)}</span>,
        }),
        column.accessor('created_at', {
          header: 'Ngày tạo',
          cell: ({ getValue }) => formatDateTime(getValue()),
        }),
        column.display({
          id: 'actions',
          header: 'Thao tác',
          cell: ({ row }) => <Actions user={row.original} onAction={onAction} />,
        }),
      ]),
    [onAction],
  )
  const table = useTable({ features, columns, data: users, getRowId: (user) => user.id })
  return (
    <div className="hidden overflow-x-auto rounded-xl border border-border xl:block">
      <table className="w-full text-left text-sm">
        <thead className="bg-muted/50">
          {table.getHeaderGroups().map((group) => (
            <tr key={group.id}>
              {group.headers.map((header) => (
                <th key={header.id} scope="col" className="px-3 py-2 font-medium">
                  <table.FlexRender header={header} />
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr key={row.id} className="border-t border-border align-top">
              {row.getAllCells().map((cell) => (
                <td key={cell.id} className="px-3 py-3">
                  <table.FlexRender cell={cell} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** Thẻ: điện thoại và tablet (dưới 1280px). */
function UserCards({ users, onAction }: ListProps) {
  return (
    <ul className="flex flex-col gap-3 xl:hidden">
      {users.map((user) => (
        <li key={user.id} className="flex flex-col gap-2 rounded-xl border border-border p-4">
          <div className="flex flex-col">
            <span className="font-medium">{user.full_name}</span>
            <span className="text-sm break-all text-muted-foreground">{user.email}</span>
          </div>
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
            <dt className="text-muted-foreground">Trạng thái</dt>
            <dd>{USER_STATUS_LABELS[user.status]}</dd>
            <dt className="text-muted-foreground">Vai trò</dt>
            <dd>{roles(user)}</dd>
            <dt className="text-muted-foreground">Yêu cầu</dt>
            <dd className="break-words">{requestInfo(user)}</dd>
            {user.reject_reason && (
              <>
                <dt className="text-muted-foreground">Lý do từ chối</dt>
                <dd className="break-words">{user.reject_reason}</dd>
              </>
            )}
            <dt className="text-muted-foreground">Ngày tạo</dt>
            <dd>{formatDateTime(user.created_at)}</dd>
          </dl>
          <Actions user={user} onAction={onAction} />
        </li>
      ))}
    </ul>
  )
}
