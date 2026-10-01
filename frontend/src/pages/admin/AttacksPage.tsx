import { ACCESS_LABEL, fixedParamLines, primaryText } from '@/admin/attack-format'
import { useAttackCatalog } from '@/admin/useAttackCatalog'
import { TruncatedId } from '@/components/CopyButton'
import { LoadError } from '@/components/LoadError'
import { PageLoading } from '@/components/PageLoading'
import { Button } from '@/components/ui/button'
import type { AttackSpecAdminView } from '@/contracts/api'
import { ATTACK_KIND_LABEL } from '@/lib/attack-kinds'

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

function ActiveBadge({ active }: { active: boolean }) {
  return active ? (
    <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200">
      Đang bật
    </span>
  ) : (
    <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">Đã tắt</span>
  )
}

const HEADERS = [
  'Tên',
  'Loại',
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
              <td className="px-3 py-3 font-medium">{spec.name}</td>
              <td className="px-3 py-3">{ATTACK_KIND_LABEL[spec.kind]}</td>
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
                <ActiveBadge active={spec.is_active} />
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
            <span className="font-medium">
              {spec.name} <span className="text-sm text-muted-foreground">v{spec.version}</span>
            </span>
            <ActiveBadge active={spec.is_active} />
          </div>
          <p className="text-sm text-muted-foreground">
            {ATTACK_KIND_LABEL[spec.kind]} · {ACCESS_LABEL[spec.access]}
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

/** Trang `/admin/attacks` (requirements.md Phase 6, Frontend; permission `attack_catalog.manage`). */
export function AttacksPage() {
  const catalog = useAttackCatalog()
  const specs = catalog.data?.pages.flatMap((page) => page.items) ?? []
  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-4 p-4 md:p-6">
      <h1 className="text-2xl font-semibold">Attack catalog</h1>
      <p className="text-sm text-muted-foreground">
        Mọi spec và version, kể cả spec đã tắt. Spec định danh bằng hash nội dung; thêm hoặc đổi
        spec qua seed catalog.
      </p>
      {catalog.isPending ? (
        <PageLoading />
      ) : catalog.isError ? (
        <LoadError onRetry={() => void catalog.refetch()} retrying={catalog.isFetching} />
      ) : specs.length === 0 ? (
        <p className="text-muted-foreground">Chưa có attack spec nào.</p>
      ) : (
        <>
          <AttackTable specs={specs} />
          <AttackCards specs={specs} />
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
        </>
      )}
    </div>
  )
}
