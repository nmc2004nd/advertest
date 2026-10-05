import { useState } from 'react'
import { useSearchParams } from 'react-router'

import { formatDateTime } from '@/admin/format'
import { errorMessage } from '@/api/messages'
import { can } from '@/auth/permissions'
import { useMe } from '@/auth/useMe'
import { THRESHOLD_KIND_LABEL } from '@/components/charts/breakpoints'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { TruncatedId } from '@/components/CopyButton'
import { FormAlert } from '@/components/FormAlert'
import { LoadError } from '@/components/LoadError'
import { PageLoading } from '@/components/PageLoading'
import { Button } from '@/components/ui/button'
import type { AttackSpec, ProtocolStatus, ProtocolSummary, ProtocolView } from '@/contracts/api'
import { criterionText } from '@/features/reviews/decision'
import { useAttackSpecs, useProtocol } from '@/features/wizard/api'

import { useAllProtocols, useCreateProtocol, useNewVersion, useRetireProtocol } from './api'
import { EMPTY_FORM, formOf } from './form'
import { ProtocolEditor } from './ProtocolEditor'
import { PageHero } from '@/layout/PageHero'
import { ProtocolArt } from '@/layout/hero-art'
import { Lock } from 'lucide-react'

const STATUS_LABEL: Record<ProtocolStatus, string> = {
  active: 'Đang dùng',
  retired: 'Đã ngừng dùng',
  dev: 'Phát triển',
}

function StatusChip({ status }: { status: ProtocolStatus }) {
  const tone =
    status === 'active'
      ? 'bg-emerald-100 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200'
      : status === 'dev'
        ? 'bg-threshold/12 text-threshold'
        : 'bg-muted text-muted-foreground'
  return <span className={`rounded-full px-2 py-0.5 text-xs ${tone}`}>{STATUS_LABEL[status]}</span>
}

/** Nội dung một version: attack bắt buộc, tiêu chí, điều kiện chung. */
export function ProtocolBodyView({ protocol }: { protocol: ProtocolView }) {
  const body = protocol.body
  return (
    <div className="space-y-3 text-sm">
      <p>{body.description}</p>
      <p className="text-muted-foreground">
        Slice tối thiểu {body.min_slice_size} ảnh · {body.cases_to_review_per_attack ?? 5} case bắt
        buộc mỗi attack ·{' '}
        {(body.forbid_dirty_runs ?? true)
          ? 'không nhận run từ code chưa commit'
          : 'nhận run từ code chưa commit'}
        {protocol.created_by &&
          ` · tạo bởi ${protocol.created_by.full_name}, ${formatDateTime(protocol.created_at)}`}
      </p>
      <div>
        <p className="font-medium">Attack bắt buộc</p>
        <ul className="list-disc pl-5">
          {body.required_attacks.map((a) => (
            <li key={a.attack_spec_name}>
              {a.attack_spec_name}:{' '}
              {a.grid
                ? `quét lưới, level ${a.grid.levels.join(', ')}`
                : a.search
                  ? `tìm ngưỡng ${THRESHOLD_KIND_LABEL[a.search.threshold_kind]} ${Math.round(a.search.threshold * 100)}% trong [${a.search.lo}, ${a.search.hi}]`
                  : ''}
            </li>
          ))}
        </ul>
      </div>
      <div>
        <p className="font-medium">Tiêu chí đạt</p>
        <ul className="list-disc pl-5">
          {body.pass_criteria.map((c, i) => (
            <li key={i}>{criterionText(c)}</li>
          ))}
        </ul>
      </div>
    </div>
  )
}

type Editing = { mode: 'create' } | { mode: 'version'; summary: ProtocolSummary } | null

function CreatePanel({ specs, onDone }: { specs: AttackSpec[]; onDone: () => void }) {
  const create = useCreateProtocol()
  return (
    <ProtocolEditor
      initial={EMPTY_FORM}
      specs={specs}
      pending={create.isPending}
      error={create.error}
      submitLabel="Tạo protocol"
      onSubmit={(name, body) => create.mutate({ name, body }, { onSuccess: onDone })}
      onCancel={onDone}
    />
  )
}

/** Version mới điền sẵn nội dung version mới nhất. */
function VersionPanel({
  summary,
  specs,
  onDone,
}: {
  summary: ProtocolSummary
  specs: AttackSpec[]
  onDone: () => void
}) {
  const version = useNewVersion(summary.id)
  const detail = useProtocol(summary.id)
  if (detail.isPending) return <p className="text-sm text-muted-foreground">Đang tải…</p>
  if (detail.isError) {
    return <LoadError onRetry={() => void detail.refetch()} retrying={detail.isFetching} />
  }
  const protocol = detail.data
  return (
    <ProtocolEditor
      initial={formOf(protocol.name, protocol.body)}
      lockName
      specs={specs}
      pending={version.isPending}
      error={version.error}
      submitLabel={`Tạo version ${protocol.version + 1}`}
      onSubmit={(_, body) => version.mutate({ body }, { onSuccess: onDone })}
      onCancel={onDone}
    />
  )
}

function ProtocolItem({
  summary,
  manage,
  onNewVersion,
  onRetire,
}: {
  summary: ProtocolSummary
  manage: boolean
  onNewVersion: (summary: ProtocolSummary) => void
  onRetire: (summary: ProtocolSummary) => void
}) {
  const [open, setOpen] = useState(false)
  const detail = useProtocol(open ? summary.id : null)
  const active = summary.status === 'active'
  return (
    <li className="space-y-2 rounded-xl border bg-surface-solid p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium break-all">{summary.name}</span>
        <span className="text-sm text-muted-foreground tabular-nums">v{summary.version}</span>
        <StatusChip status={summary.status} />
        <TruncatedId value={summary.body_sha256} />
      </div>
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
          {open ? 'Ẩn nội dung' : 'Xem nội dung'}
        </Button>
        {manage && active && (
          <>
            <Button variant="outline" onClick={() => onNewVersion(summary)}>
              Tạo version mới
            </Button>
            <Button variant="outline" onClick={() => onRetire(summary)}>
              Ngừng dùng
            </Button>
          </>
        )}
      </div>
      {open &&
        (detail.isPending ? (
          <p className="text-sm text-muted-foreground">Đang tải…</p>
        ) : detail.isError ? (
          <LoadError onRetry={() => void detail.refetch()} retrying={detail.isFetching} />
        ) : (
          <ProtocolBodyView protocol={detail.data} />
        ))}
    </li>
  )
}

/**
 * Protocol (requirements.md Phase 8, Frontend reviewer; plan task 30). Mọi người có
 * `protocol.read` xem; tạo, tạo version mới và ngừng dùng cần `protocol.manage`.
 */
export function ProtocolsPage() {
  const { data: me } = useMe()
  const manage = can(me, 'protocol.manage')
  const protocols = useAllProtocols()
  const specs = useAttackSpecs()
  const retire = useRetireProtocol()
  // `?new=1` (nút "Tạo protocol" ở trang chủ) mở sẵn form tạo: bớt một cú bấm.
  const [params] = useSearchParams()
  const [editing, setEditing] = useState<Editing>(() =>
    manage && params.get('new') === '1' ? { mode: 'create' } : null,
  )
  const [retiring, setRetiring] = useState<ProtocolSummary | null>(null)

  if (protocols.isPending) return <PageLoading />
  if (protocols.isError) {
    return (
      <div className="p-4 md:p-6">
        <LoadError onRetry={() => void protocols.refetch()} retrying={protocols.isFetching} />
      </div>
    )
  }
  const order: ProtocolStatus[] = ['active', 'dev', 'retired']
  const sorted = [...protocols.data].sort(
    (a, b) =>
      order.indexOf(a.status) - order.indexOf(b.status) ||
      a.name.localeCompare(b.name) ||
      b.version - a.version,
  )
  const catalog = specs.data ?? []

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-5 p-4 md:p-8">
      <PageHero
        art={<ProtocolArt />}
        title="Protocol"
        description="Protocol là luật chơi được chốt trước khi ai biết kết quả: phải chạy attack nào, ở mức nào, trên bao nhiêu ảnh, và thế nào là đạt."
        actions={
          manage && editing === null ? (
            <Button onClick={() => setEditing({ mode: 'create' })}>Tạo protocol</Button>
          ) : undefined
        }
      >
        <p className="flex items-center gap-2 text-[13.5px] text-muted-foreground">
          <Lock className="size-3.5 shrink-0" aria-hidden />
          Không sửa được sau khi tạo: muốn đổi thì tạo version mới, version cũ tự ngừng dùng.
        </p>
      </PageHero>
      {editing && (
        <section className="panel space-y-4 p-5 md:p-7" aria-label="Biên soạn protocol">
          <h2 className="text-lg font-semibold">
            {editing.mode === 'create' ? 'Tạo protocol' : `Version mới của ${editing.summary.name}`}
          </h2>
          {specs.isError && <FormAlert>Không tải được attack catalog.</FormAlert>}
          {editing.mode === 'create' ? (
            <CreatePanel specs={catalog} onDone={() => setEditing(null)} />
          ) : (
            <VersionPanel
              summary={editing.summary}
              specs={catalog}
              onDone={() => setEditing(null)}
            />
          )}
        </section>
      )}
      {retire.isError && <FormAlert>{errorMessage(retire.error)}</FormAlert>}
      {sorted.length === 0 ? (
        <p className="text-muted-foreground">Chưa có protocol nào.</p>
      ) : (
        <ul className="grid gap-3">
          {sorted.map((p) => (
            <ProtocolItem
              key={p.id}
              summary={p}
              manage={manage}
              onNewVersion={(summary) => setEditing({ mode: 'version', summary })}
              onRetire={setRetiring}
            />
          ))}
        </ul>
      )}
      <ConfirmDialog
        open={retiring !== null}
        onOpenChange={(open) => !open && setRetiring(null)}
        title="Ngừng dùng protocol?"
        description="Experiment mới không chọn được protocol này nữa. Experiment đã dùng nó không đổi."
        confirmLabel="Ngừng dùng"
        destructive
        pending={retire.isPending}
        onConfirm={() =>
          retiring && retire.mutate(retiring.id, { onSettled: () => setRetiring(null) })
        }
      >
        <p className="text-sm">
          {retiring?.name} v{retiring?.version}
        </p>
      </ConfirmDialog>
    </div>
  )
}
