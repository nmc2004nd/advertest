import { Plus } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router'

import { ACCESS_LABEL, fixedParamLines, primaryText } from '@/admin/attack-format'
import { adapterOf } from '@/admin/spec-form'
import { useAttackCatalog } from '@/admin/useAttackCatalog'
import { TruncatedId } from '@/components/CopyButton'
import { SelectField } from '@/components/form/TextField'
import { LoadError } from '@/components/LoadError'
import { PageLoading } from '@/components/PageLoading'
import { ATTACK_SPEC_STATUS } from '@/components/status/status-config'
import { StatusBadge } from '@/components/status/StatusBadge'
import { Button } from '@/components/ui/button'
import type { AttackSpecAdminView, AttackSpecStatus } from '@/contracts/api'
import { attackSpecStatusValues } from '@/contracts/schemas'
import { ATTACK_KIND_LABEL } from '@/lib/attack-kinds'
import { PageHero } from '@/layout/PageHero'

function FixedParams({ spec }: { spec: AttackSpecAdminView }) {
  const lines = fixedParamLines(spec)
  if (lines.length === 0) return <span className="text-muted-foreground">—</span>
  return (
    <ul className="flex flex-col gap-0.5 font-mono text-xs break-all">
      {lines.map((line) => (
        <li key={line}>{line}</li>
      ))}
    </ul>
  )
}

/** Tên dễ đọc (metadata) kèm tên kỹ thuật; link sang trang chi tiết spec. */
function SpecName({ spec }: { spec: AttackSpecAdminView }) {
  return (
    <Link
      to={`/admin/attacks/${spec.id}`}
      className="font-medium text-cta underline-offset-4 hover:underline focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
    >
      {spec.metadata?.display_name ?? spec.name}
    </Link>
  )
}

const HEADERS = [
  'Tên',
  'Loại',
  'Adapter',
  'Access',
  'Tham số chính',
  'Tham số cố định',
  'Version',
  'Hash',
  'Trạng thái',
]

/** Bảng: chỉ hiện từ 1280px (desktop). */
function AttackTable({ specs }: { specs: AttackSpecAdminView[] }) {
  return (
    <div className="hidden overflow-x-auto rounded-xl border border-border xl:block">
      <table className="w-full text-left text-sm">
        <caption className="sr-only">Attack catalog</caption>
        <thead className="bg-muted/50">
          <tr>
            {HEADERS.map((h) => (
              <th key={h} scope="col" className="px-3 py-2 font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {specs.map((spec) => (
            <tr key={spec.id} className="border-t border-border align-top">
              <td className="px-3 py-3">
                <SpecName spec={spec} />
                {spec.metadata && (
                  <span className="block font-mono text-xs text-muted-foreground">{spec.name}</span>
                )}
              </td>
              <td className="px-3 py-3">{ATTACK_KIND_LABEL[spec.kind]}</td>
              <td className="px-3 py-3 font-mono text-xs">{adapterOf(spec)}</td>
              <td className="px-3 py-3">{ACCESS_LABEL[spec.access]}</td>
              <td className="px-3 py-3 tabular-nums">{primaryText(spec)}</td>
              <td className="px-3 py-3">
                <FixedParams spec={spec} />
              </td>
              <td className="px-3 py-3 tabular-nums">v{spec.version}</td>
              <td className="px-3 py-1">
                <TruncatedId value={spec.spec_sha256} />
              </td>
              <td className="px-3 py-3">
                <StatusBadge kind="attack_spec" status={spec.status} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** Thẻ: điện thoại và tablet (dưới 1280px). */
function AttackCards({ specs }: { specs: AttackSpecAdminView[] }) {
  return (
    <ul className="flex flex-col gap-3 xl:hidden">
      {specs.map((spec) => (
        <li key={spec.id} className="flex flex-col gap-2 rounded-xl border border-border p-4">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <span>
              <SpecName spec={spec} />{' '}
              <span className="text-sm text-muted-foreground">v{spec.version}</span>
            </span>
            <StatusBadge kind="attack_spec" status={spec.status} />
          </div>
          <p className="text-sm text-muted-foreground">
            {spec.metadata && <span className="font-mono">{spec.name} · </span>}
            {ATTACK_KIND_LABEL[spec.kind]} · {ACCESS_LABEL[spec.access]} ·{' '}
            <span className="font-mono">{adapterOf(spec)}</span>
          </p>
          <p className="text-sm tabular-nums">{primaryText(spec)}</p>
          <FixedParams spec={spec} />
          <span className="text-xs text-muted-foreground">
            Hash <TruncatedId value={spec.spec_sha256} />
          </span>
        </li>
      ))}
    </ul>
  )
}

/** Trang `/admin/attacks` (Phase 6; Phase R3: trạng thái, bộ lọc, tạo spec qua giao diện). */
export function AttacksPage() {
  const navigate = useNavigate()
  const catalog = useAttackCatalog()
  const [status, setStatus] = useState<AttackSpecStatus | ''>('')
  const all = catalog.data?.pages.flatMap((page) => page.items) ?? []
  const specs = status ? all.filter((spec) => spec.status === status) : all
  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-5 p-4 md:p-8">
      <PageHero
        compact
        title="Attack catalog"
        description="Mọi spec và version, kể cả spec đã thay thế. Spec mới được worker tự kiểm tra, rồi một reviewer kích hoạt trước khi xuất hiện trong wizard."
        actions={
          <Button size="lg" onClick={() => void navigate('/admin/attacks/new')}>
            <Plus aria-hidden />
            Tạo attack spec
          </Button>
        }
      />
      <div className="sm:w-72">
        <SelectField
          label="Trạng thái"
          value={status}
          onChange={(event) => setStatus(event.target.value as AttackSpecStatus | '')}
        >
          <option value="">Mọi trạng thái</option>
          {attackSpecStatusValues.map((value) => (
            <option key={value} value={value}>
              {ATTACK_SPEC_STATUS[value].label}
            </option>
          ))}
        </SelectField>
      </div>
      {catalog.isPending ? (
        <PageLoading />
      ) : catalog.isError ? (
        <LoadError onRetry={() => void catalog.refetch()} retrying={catalog.isFetching} />
      ) : specs.length === 0 ? (
        <p className="text-muted-foreground">
          {status
            ? 'Không có spec nào ở trạng thái này trong các trang đã tải.'
            : 'Chưa có attack spec nào.'}
        </p>
      ) : (
        <>
          <AttackTable specs={specs} />
          <AttackCards specs={specs} />
        </>
      )}
      {catalog.hasNextPage && (
        <Button
          variant="outline"
          className="self-center"
          disabled={catalog.isFetchingNextPage}
          onClick={() => void catalog.fetchNextPage()}
        >
          {catalog.isFetchingNextPage ? 'Đang tải…' : 'Tải thêm'}
        </Button>
      )}
    </div>
  )
}
