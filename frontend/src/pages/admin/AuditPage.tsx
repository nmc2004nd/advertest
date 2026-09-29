import { useQuery } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'

import { actionLabel, AUDIT_ACTION_LABELS, describeChange, formatDateTime } from '@/admin/format'
import { EMPTY_FILTERS, useAuditLog, type AuditFilters } from '@/admin/useAudit'
import { ADMIN_USERS_KEY } from '@/admin/useUsers'
import { apiGet } from '@/api/client'
import { useCan } from '@/auth/useMe'
import { TruncatedId } from '@/components/CopyButton'
import { SelectField, TextField } from '@/components/form/TextField'
import { LoadError } from '@/components/LoadError'
import { PageLoading } from '@/components/PageLoading'
import { Button } from '@/components/ui/button'
import type { AuditLogEntry, UserAdminPage } from '@/contracts/schemas'

export function AuditPage() {
  const [draft, setDraft] = useState<AuditFilters>(EMPTY_FILTERS)
  const [filters, setFilters] = useState<AuditFilters>(EMPTY_FILTERS)
  const log = useAuditLog(filters)
  const entries = log.data?.pages.flatMap((page) => page.items) ?? []
  const apply = (next: AuditFilters) => {
    setDraft(next)
    setFilters(next)
  }
  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    apply(draft)
  }
  const filterByActor = (actorId: string) => apply({ ...filters, actorId })

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-4 p-4 md:p-6">
      <h1 className="text-2xl font-semibold">Audit log</h1>
      <form
        onSubmit={onSubmit}
        aria-label="Bộ lọc audit log"
        className="grid gap-3 rounded-xl border border-border p-4 md:grid-cols-2 xl:grid-cols-5"
      >
        <ActorSelect
          value={draft.actorId}
          onChange={(actorId) => setDraft({ ...draft, actorId })}
        />
        <SelectField
          label="Hành động"
          value={draft.action}
          onChange={(event) => setDraft({ ...draft, action: event.target.value })}
        >
          <option value="">Tất cả</option>
          {Object.entries(AUDIT_ACTION_LABELS).map(([action, label]) => (
            <option key={action} value={action}>
              {label}
            </option>
          ))}
        </SelectField>
        <TextField
          label="Loại đối tượng"
          placeholder="ví dụ: user"
          value={draft.entityType}
          onChange={(event) => setDraft({ ...draft, entityType: event.target.value })}
        />
        <TextField
          label="Từ ngày"
          type="date"
          value={draft.from}
          onChange={(event) => setDraft({ ...draft, from: event.target.value })}
        />
        <TextField
          label="Đến ngày"
          type="date"
          value={draft.to}
          onChange={(event) => setDraft({ ...draft, to: event.target.value })}
        />
        <div className="flex gap-2 md:col-span-2 xl:col-span-5">
          <Button type="submit">Lọc</Button>
          <Button type="button" variant="outline" onClick={() => apply(EMPTY_FILTERS)}>
            Xóa lọc
          </Button>
        </div>
      </form>
      {log.isPending ? (
        <PageLoading />
      ) : log.isError ? (
        <LoadError onRetry={() => void log.refetch()} retrying={log.isFetching} />
      ) : entries.length === 0 ? (
        <p className="text-muted-foreground">Không có dòng nào khớp bộ lọc.</p>
      ) : (
        <>
          <AuditTable entries={entries} onActor={filterByActor} />
          <AuditCards entries={entries} onActor={filterByActor} />
          {log.hasNextPage && (
            <Button
              variant="outline"
              className="self-center"
              disabled={log.isFetchingNextPage}
              onClick={() => void log.fetchNextPage()}
            >
              {log.isFetchingNextPage ? 'Đang tải…' : 'Tải thêm'}
            </Button>
          )}
        </>
      )}
    </div>
  )
}

/**
 * Chọn người thực hiện từ danh sách người dùng (tối đa 100, người dùng chốt ở Group 6). Chỉ tải
 * khi có `user.manage`; không có thì ẩn ô này (vẫn lọc được bằng cách nhấn actor trong danh sách).
 */
function ActorSelect({ value, onChange }: { value: string; onChange: (id: string) => void }) {
  const canListUsers = useCan('user.manage')
  const users = useQuery({
    queryKey: [...ADMIN_USERS_KEY, 'actor-options'],
    queryFn: () => apiGet<UserAdminPage>('/admin/users?limit=100'),
    enabled: canListUsers,
  })
  if (!canListUsers) return null
  return (
    <SelectField label="Người thực hiện" value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">Tất cả</option>
      {users.data?.items.map((user) => (
        <option key={user.id} value={user.id}>
          {user.full_name} ({user.email})
        </option>
      ))}
    </SelectField>
  )
}

interface ListProps {
  entries: AuditLogEntry[]
  onActor: (actorId: string) => void
}

function Actor({ entry, onActor }: { entry: AuditLogEntry } & Pick<ListProps, 'onActor'>) {
  if (!entry.actor) return <span className="text-muted-foreground">Hệ thống</span>
  const actor = entry.actor
  return (
    <button
      type="button"
      className="inline-flex min-h-11 flex-col items-start justify-center text-left underline-offset-4 hover:underline focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
      title="Lọc theo người này"
      onClick={() => onActor(actor.id)}
    >
      <span>{actor.full_name}</span>
      <span className="text-xs break-all text-muted-foreground">{actor.email}</span>
    </button>
  )
}

function Changes({ entry }: { entry: AuditLogEntry }) {
  const lines = describeChange(entry)
  if (lines.length === 0) return <span className="text-muted-foreground">—</span>
  return (
    <ul className="flex flex-col gap-0.5 font-mono text-xs break-all">
      {lines.map((line) => (
        <li key={line}>{line}</li>
      ))}
    </ul>
  )
}

function Entity({ entry }: { entry: AuditLogEntry }) {
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      <span>{entry.entity_type}</span>
      {entry.entity_id && <TruncatedId value={entry.entity_id} />}
    </span>
  )
}

/** Bảng: chỉ hiện từ 1280px (desktop). */
function AuditTable({ entries, onActor }: ListProps) {
  return (
    <div className="hidden overflow-x-auto rounded-xl border border-border xl:block">
      <table className="w-full text-left text-sm">
        <thead className="bg-muted/50">
          <tr>
            {['Thời gian', 'Người thực hiện', 'Hành động', 'Đối tượng', 'Thay đổi', 'ID'].map(
              (h) => (
                <th key={h} scope="col" className="px-3 py-2 font-medium">
                  {h}
                </th>
              ),
            )}
          </tr>
        </thead>
        <tbody>
          {entries.map((entry) => (
            <tr key={entry.id} className="border-t border-border align-top">
              <td className="px-3 py-3 whitespace-nowrap">{formatDateTime(entry.created_at)}</td>
              <td className="px-3 py-1">
                <Actor entry={entry} onActor={onActor} />
              </td>
              <td className="px-3 py-3">{actionLabel(entry.action)}</td>
              <td className="px-3 py-3">
                <Entity entry={entry} />
              </td>
              <td className="px-3 py-3">
                <Changes entry={entry} />
              </td>
              <td className="px-3 py-3">
                <TruncatedId value={entry.id} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** Thẻ: điện thoại và tablet (dưới 1280px). */
function AuditCards({ entries, onActor }: ListProps) {
  return (
    <ul className="flex flex-col gap-3 xl:hidden">
      {entries.map((entry) => (
        <li key={entry.id} className="flex flex-col gap-2 rounded-xl border border-border p-4">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <span className="font-medium">{actionLabel(entry.action)}</span>
            <span className="text-sm text-muted-foreground">
              {formatDateTime(entry.created_at)}
            </span>
          </div>
          <Actor entry={entry} onActor={onActor} />
          <Entity entry={entry} />
          <Changes entry={entry} />
          <span className="text-xs text-muted-foreground">
            ID <TruncatedId value={entry.id} />
          </span>
        </li>
      ))}
    </ul>
  )
}
