import { FilePlus2, PencilLine, RotateCw, SearchX } from 'lucide-react'
import { type ReactNode, useState } from 'react'
import { useNavigate, useParams } from 'react-router'

import { errorMessage } from '@/api/messages'
import { ACCESS_LABEL, fixedParamLines, primaryText } from '@/admin/attack-format'
import { MetadataDialog } from '@/admin/MetadataDialog'
import { SpecCheckList } from '@/admin/SpecCheckList'
import { adapterOf } from '@/admin/spec-form'
import { useAdminSpec, useRecheckSpec, useRejectReason } from '@/admin/useSpecAdmin'
import { TruncatedId } from '@/components/CopyButton'
import { EmptyState } from '@/components/EmptyState'
import { FormAlert } from '@/components/FormAlert'
import { LoadError } from '@/components/LoadError'
import { PageLoading } from '@/components/PageLoading'
import { StatusBadge } from '@/components/status/StatusBadge'
import { Button } from '@/components/ui/button'
import type { AttackSpecAdminView } from '@/contracts/api'
import { CATALOG_COPY, REALISM_LABEL } from '@/copy/catalog'
import { ATTACK_KIND_LABEL } from '@/lib/attack-kinds'
import { PageHeader } from '@/layout/PageHeader'

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid gap-1 py-2 sm:grid-cols-[11rem_1fr] sm:gap-3">
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd className="min-w-0 text-sm">{children}</dd>
    </div>
  )
}

function SpecBody({ spec }: { spec: AttackSpecAdminView }) {
  const lines = fixedParamLines(spec)
  const cost = spec.cost_model.cpu_only
    ? 'Chỉ CPU'
    : `${spec.cost_model.passes_per_image ?? '—'} lượt forward + backward mỗi ảnh`
  return (
    <dl className="divide-y divide-border">
      <Row label="Loại">{ATTACK_KIND_LABEL[spec.kind]}</Row>
      <Row label="Adapter">
        <span className="font-mono text-xs">{adapterOf(spec)}</span>
      </Row>
      <Row label="Access">{ACCESS_LABEL[spec.access]}</Row>
      {spec.art_class && (
        <Row label="Lớp ART">
          <span className="font-mono text-xs">{spec.art_class}</span>
        </Row>
      )}
      <Row label="Dải level">
        <span className="tabular-nums">{primaryText(spec)}</span>
        {spec.primary_param.values && (
          <span className="block text-muted-foreground tabular-nums">
            Các level: {spec.primary_param.values.join(', ')}
          </span>
        )}
      </Row>
      <Row label="Tham số cố định">
        {lines.length === 0 ? (
          '—'
        ) : (
          <ul className="flex flex-col gap-0.5 font-mono text-xs break-all">
            {lines.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        )}
      </Row>
      <Row label="Chi phí">{cost}</Row>
      <Row label="Cần gradient">{spec.requires_gradients ? 'Có' : 'Không'}</Row>
      <Row label="Hash">
        <TruncatedId value={spec.spec_sha256} />
      </Row>
      <Row label="Người tạo">{spec.created_by?.full_name ?? 'Seed catalog'}</Row>
      {spec.approved_by && <Row label="Người kích hoạt">{spec.approved_by.full_name}</Row>}
    </dl>
  )
}

function Metadata({ spec }: { spec: AttackSpecAdminView }) {
  const meta = spec.metadata
  if (!meta) {
    return <p className="text-sm text-muted-foreground">Spec seed chưa có thông tin hiển thị.</p>
  }
  const labels = Object.entries(meta.level_labels ?? {})
  return (
    <dl className="divide-y divide-border">
      <Row label="Tên hiển thị">{meta.display_name}</Row>
      <Row label="Mô tả">{meta.description}</Row>
      <Row label="Mức sát thực tế">{REALISM_LABEL[meta.realism]}</Row>
      <Row label="Nhãn level">
        {labels.length === 0
          ? '—'
          : labels.map(([level, label]) => `${level}: ${label}`).join(' · ')}
      </Row>
    </dl>
  )
}

function RejectedNote({ spec }: { spec: AttackSpecAdminView }) {
  const reason = useRejectReason(spec.id, true)
  return (
    <FormAlert>
      {reason.data && <span className="block font-semibold">Lý do từ chối: {reason.data}</span>}
      {CATALOG_COPY.rejectedNote}
    </FormAlert>
  )
}

function SpecDetail({ spec }: { spec: AttackSpecAdminView }) {
  const navigate = useNavigate()
  const recheck = useRecheckSpec()
  const [editing, setEditing] = useState(false)
  // Spec nháp đã qua kiểm tra chỉ có thể là spec bị reviewer từ chối (pending_approval → draft).
  const rejected = spec.status === 'draft' && spec.check?.passed === true
  return (
    <>
      <PageHeader
        back={{ to: '/admin/attacks', label: 'Attack catalog' }}
        eyebrow={`${spec.name} v${spec.version}`}
        title={spec.metadata?.display_name ?? spec.name}
        description={spec.metadata?.description}
        actions={
          <>
            {spec.status === 'check_failed' && (
              <Button disabled={recheck.isPending} onClick={() => recheck.mutate(spec.id)}>
                <RotateCw aria-hidden />
                Kiểm tra lại
              </Button>
            )}
            <Button variant="outline" onClick={() => setEditing(true)}>
              <PencilLine aria-hidden />
              Sửa metadata
            </Button>
            <Button
              variant="outline"
              onClick={() => void navigate(`/admin/attacks/new?from=${spec.id}&mode=version`)}
            >
              <FilePlus2 aria-hidden />
              Tạo version mới
            </Button>
          </>
        }
      />
      <div className="flex flex-wrap items-center gap-3">
        <span data-testid="spec-status">
          <StatusBadge kind="attack_spec" status={spec.status} />
        </span>
        {spec.status === 'checking' && (
          <span className="text-sm text-muted-foreground">{CATALOG_COPY.checkingNote}</span>
        )}
      </div>
      {recheck.isError && <FormAlert>{errorMessage(recheck.error)}</FormAlert>}
      {rejected && <RejectedNote spec={spec} />}
      <div className="grid gap-5 lg:grid-cols-2">
        <section className="panel flex flex-col gap-3 p-5" aria-label="Tự kiểm tra">
          <h2 className="text-base font-semibold">Tự kiểm tra</h2>
          <SpecCheckList check={spec.check} />
        </section>
        <div className="flex flex-col gap-5">
          <section className="panel flex flex-col gap-2 p-5" aria-label="Nội dung spec">
            <h2 className="text-base font-semibold">Nội dung spec</h2>
            <SpecBody spec={spec} />
          </section>
          <section className="panel flex flex-col gap-2 p-5" aria-label="Thông tin hiển thị">
            <h2 className="text-base font-semibold">Thông tin hiển thị</h2>
            <Metadata spec={spec} />
          </section>
        </div>
      </div>
      {editing && <MetadataDialog spec={spec} onClose={() => setEditing(false)} />}
    </>
  )
}

/** `/admin/attacks/:id`: kết quả tự kiểm tra, tự cập nhật khi đang kiểm tra (Phase R3). */
export function SpecDetailPage() {
  const { id = '' } = useParams()
  const query = useAdminSpec(id)
  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-5 p-4 md:p-8">
      {query.isPending ? (
        <PageLoading />
      ) : query.isError ? (
        <LoadError onRetry={() => void query.refetch()} retrying={query.isFetching} />
      ) : query.spec ? (
        <SpecDetail spec={query.spec} />
      ) : (
        <EmptyState icon={SearchX} title="Không tìm thấy spec">
          Spec này không có trong catalog. Quay lại Attack catalog để chọn spec khác.
        </EmptyState>
      )}
    </div>
  )
}
