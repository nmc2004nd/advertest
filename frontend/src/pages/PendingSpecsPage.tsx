import { BadgeCheck, ClipboardCheck, X } from 'lucide-react'
import { useState } from 'react'

import { errorMessage } from '@/api/messages'
import { primaryText } from '@/admin/attack-format'
import { SpecCheckList } from '@/admin/SpecCheckList'
import { specChanges } from '@/admin/spec-diff'
import { adapterOf } from '@/admin/spec-form'
import {
  useActiveSpecs,
  useApproveSpec,
  usePendingSpecs,
  useRejectSpec,
} from '@/admin/useSpecAdmin'
import { useMe } from '@/auth/useMe'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { EmptyState } from '@/components/EmptyState'
import { FormAlert } from '@/components/FormAlert'
import { TextareaField } from '@/components/form/TextField'
import { LoadError } from '@/components/LoadError'
import { PageLoading } from '@/components/PageLoading'
import { StatusBadge } from '@/components/status/StatusBadge'
import { Button } from '@/components/ui/button'
import type { AttackSpecAdminView, AttackSpecView } from '@/contracts/api'
import { CATALOG_COPY } from '@/copy/catalog'
import { ATTACK_KIND_LABEL } from '@/lib/attack-kinds'
import { PageHero } from '@/layout/PageHero'

function specLabel(spec: { name: string; version: number }): string {
  return `${spec.name} v${spec.version}`
}

function Changes({ spec, active }: { spec: AttackSpecAdminView; active?: AttackSpecView }) {
  if (!active) {
    return (
      <p className="text-sm text-muted-foreground">
        Tên mới: chưa có version nào đang dùng để so sánh.
      </p>
    )
  }
  const changes = specChanges(active, spec)
  return (
    <div className="flex flex-col gap-2">
      <p className="text-sm text-muted-foreground">
        So với {specLabel(active)} đang dùng:{' '}
        {changes.length === 0 ? 'phần thân không khác.' : `${changes.length} trường khác.`}
      </p>
      {changes.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-border">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Khác biệt với {specLabel(active)}</caption>
            <thead className="bg-muted/50">
              <tr>
                <th scope="col" className="px-3 py-2 font-medium">
                  Trường
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  {specLabel(active)}
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  {specLabel(spec)}
                </th>
              </tr>
            </thead>
            <tbody>
              {changes.map((c) => (
                <tr key={c.field} className="border-t border-border align-top">
                  <td className="px-3 py-2 font-mono text-xs">{c.field}</td>
                  <td className="px-3 py-2 font-mono text-xs break-all">{c.before}</td>
                  <td className="px-3 py-2 font-mono text-xs break-all">{c.after}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function ApproveDialog({
  spec,
  active,
  onClose,
}: {
  spec: AttackSpecAdminView
  active?: AttackSpecView
  onClose: () => void
}) {
  const approve = useApproveSpec()
  return (
    <ConfirmDialog
      open
      onOpenChange={(open) => !open && onClose()}
      title={`Kích hoạt ${specLabel(spec)}?`}
      description={CATALOG_COPY.approveConsequence}
      confirmLabel="Kích hoạt"
      pending={approve.isPending}
      onConfirm={() => approve.mutate(spec.id, { onSuccess: onClose })}
    >
      {active && (
        <p className="text-sm">
          <span className="font-semibold">{specLabel(active)}</span> sẽ chuyển sang Đã thay thế.
        </p>
      )}
      {approve.isError && <FormAlert>{errorMessage(approve.error)}</FormAlert>}
    </ConfirmDialog>
  )
}

function RejectDialog({ spec, onClose }: { spec: AttackSpecAdminView; onClose: () => void }) {
  const [reason, setReason] = useState('')
  const reject = useRejectSpec()
  return (
    <ConfirmDialog
      open
      onOpenChange={(open) => !open && onClose()}
      title={`Từ chối ${specLabel(spec)}?`}
      description={CATALOG_COPY.rejectConsequence}
      confirmLabel="Từ chối"
      destructive
      pending={reject.isPending}
      canConfirm={reason.trim().length > 0}
      onConfirm={() =>
        reject.mutate({ id: spec.id, reason: reason.trim() }, { onSuccess: onClose })
      }
    >
      <TextareaField
        label="Lý do"
        hint="Bắt buộc. Người tạo spec sẽ thấy lý do này."
        value={reason}
        maxLength={2000}
        onChange={(e) => setReason(e.target.value)}
      />
      {reject.isError && <FormAlert>{errorMessage(reject.error)}</FormAlert>}
    </ConfirmDialog>
  )
}

export function PendingSpecCard({
  spec,
  active,
  own,
  onApprove,
  onReject,
}: {
  spec: AttackSpecAdminView
  active?: AttackSpecView
  own: boolean
  onApprove: () => void
  onReject: () => void
}) {
  const passed = spec.check?.items.filter((i) => i.passed).length ?? 0
  return (
    <li data-testid="pending-spec" className="panel flex flex-col gap-4 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <h2 className="text-base font-semibold">{spec.metadata?.display_name ?? spec.name}</h2>
          <p className="text-sm text-muted-foreground">
            <span className="font-mono">{specLabel(spec)}</span> · {ATTACK_KIND_LABEL[spec.kind]} ·{' '}
            <span className="font-mono">{adapterOf(spec)}</span> · {primaryText(spec)}
          </p>
          <p className="text-sm text-muted-foreground">
            Người tạo: {spec.created_by?.full_name ?? 'Seed catalog'}
          </p>
        </div>
        <StatusBadge kind="attack_spec" status={spec.status} />
      </div>
      {spec.metadata?.description && (
        <p className="max-w-[62ch] text-sm">{spec.metadata.description}</p>
      )}
      <Changes spec={spec} active={active} />
      <details className="group">
        <summary className="cursor-pointer text-sm font-semibold">
          Tự kiểm tra: {passed}/7 mục đạt
        </summary>
        <div className="mt-3">
          <SpecCheckList check={spec.check} />
        </div>
      </details>
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-end">
        {own && <p className="text-sm text-muted-foreground md:mr-auto">{CATALOG_COPY.ownSpec}</p>}
        <Button variant="outline" disabled={own} onClick={onReject}>
          <X aria-hidden />
          Từ chối
        </Button>
        <Button disabled={own} onClick={onApprove}>
          <BadgeCheck aria-hidden />
          Kích hoạt
        </Button>
      </div>
    </li>
  )
}

/**
 * `/attack-specs/pending` (requirements.md Phase R3, mục Reviewer duyệt spec): spec chờ kích hoạt.
 * Spec do chính mình tạo thì nút bị vô hiệu (nguyên tắc 1); backend vẫn là lớp chặn.
 */
export function PendingSpecsPage() {
  const { data: me } = useMe()
  const pending = usePendingSpecs()
  const active = useActiveSpecs()
  const [dialog, setDialog] = useState<{ kind: 'approve' | 'reject'; spec: AttackSpecAdminView }>()
  const activeOf = (spec: AttackSpecAdminView) =>
    active.data?.find((a) => a.name === spec.name && a.id !== spec.id)

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-5 p-4 md:p-8">
      <PageHero
        compact
        title="Spec chờ kích hoạt"
        description="Spec mới đã qua tự kiểm tra. Kích hoạt để spec có trong wizard, hoặc từ chối kèm lý do. Bạn không kích hoạt được spec do chính mình tạo."
      />
      {pending.isPending ? (
        <PageLoading />
      ) : pending.isError ? (
        <LoadError onRetry={() => void pending.refetch()} retrying={pending.isFetching} />
      ) : pending.data.length === 0 ? (
        <EmptyState icon={ClipboardCheck} title="Không có spec nào chờ kích hoạt">
          Spec admin tạo sẽ xuất hiện ở đây sau khi qua tự kiểm tra.
        </EmptyState>
      ) : (
        <ul className="flex flex-col gap-4">
          {pending.data.map((spec) => (
            <PendingSpecCard
              key={spec.id}
              spec={spec}
              active={activeOf(spec)}
              own={me !== undefined && spec.created_by?.id === me.id}
              onApprove={() => setDialog({ kind: 'approve', spec })}
              onReject={() => setDialog({ kind: 'reject', spec })}
            />
          ))}
        </ul>
      )}
      {dialog?.kind === 'approve' && (
        <ApproveDialog
          spec={dialog.spec}
          active={activeOf(dialog.spec)}
          onClose={() => setDialog(undefined)}
        />
      )}
      {dialog?.kind === 'reject' && (
        <RejectDialog spec={dialog.spec} onClose={() => setDialog(undefined)} />
      )}
    </div>
  )
}
