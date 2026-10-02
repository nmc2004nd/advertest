import { Keyboard } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'

import { formatDateTime } from '@/admin/format'
import { useMe } from '@/auth/useMe'
import { errorMessage } from '@/api/messages'
import { CaseViewer } from '@/components/case-viewer/CaseViewer'
import { FormAlert } from '@/components/FormAlert'
import { LoadError } from '@/components/LoadError'
import { PageLoading } from '@/components/PageLoading'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import type { CaseVerdictView } from '@/contracts/api'
import { useExperiment, useFailureCase, useRetryOnImageError } from '@/features/experiments/api'
import { cn } from '@/lib/utils'

import { useAddVerdict, useVerdicts } from './api'
import {
  applyShortcut,
  isTextField,
  KIND_LABEL,
  KINDS,
  neighbours,
  SEVERITIES,
  SEVERITY_LABEL,
  shortcutOf,
  SHORTCUTS,
  type VerdictDraft,
  verdictBody,
} from './verdict'

const EMPTY: VerdictDraft = { severity: null, kind: null, mitigation: '' }

function draftOf(verdict: CaseVerdictView | undefined): VerdictDraft {
  return verdict
    ? { severity: verdict.severity, kind: verdict.kind, mitigation: verdict.mitigation ?? '' }
    : EMPTY
}

/** Nút chọn lớn (vùng chạm ≥ 44px), kèm phím tắt. */
function Choice({
  selected,
  label,
  shortcut,
  disabled,
  onClick,
}: {
  selected: boolean
  label: string
  shortcut: string
  disabled: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        'flex min-h-12 items-center justify-between gap-2 rounded-lg border px-3 text-left text-sm',
        selected ? 'border-primary bg-primary/10 ring-2 ring-primary/30' : 'hover:bg-muted',
        disabled && 'cursor-not-allowed opacity-60',
      )}
    >
      {label}
      <kbd className="rounded border bg-muted px-1.5 text-xs text-muted-foreground">{shortcut}</kbd>
    </button>
  )
}

/** Form verdict (dùng cả ở cột phải desktop và bottom sheet điện thoại). */
export function VerdictForm({
  draft,
  onChange,
  onSave,
  saving,
  error,
  disabled,
  idPrefix,
}: {
  draft: VerdictDraft
  onChange: (draft: VerdictDraft) => void
  onSave: () => void
  saving: boolean
  error: string | null
  disabled: boolean
  idPrefix: string
}) {
  const check = verdictBody(draft)
  return (
    <div className="space-y-3">
      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">Mức nghiêm trọng</legend>
        <div role="radiogroup" aria-label="Mức nghiêm trọng" className="grid grid-cols-2 gap-2">
          {SEVERITIES.map((s) => (
            <Choice
              key={s.value}
              selected={draft.severity === s.value}
              label={s.label}
              shortcut={s.key}
              disabled={disabled}
              onClick={() => onChange({ ...draft, severity: s.value })}
            />
          ))}
        </div>
      </fieldset>
      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">Loại verdict</legend>
        <div role="radiogroup" aria-label="Loại verdict" className="grid gap-2">
          {KINDS.map((k) => (
            <Choice
              key={k.value}
              selected={draft.kind === k.value}
              label={k.label}
              shortcut={k.key}
              disabled={disabled}
              onClick={() => onChange({ ...draft, kind: k.value })}
            />
          ))}
        </div>
      </fieldset>
      <div className="flex flex-col gap-1.5">
        <label htmlFor={`${idPrefix}-khac-phuc`} className="text-sm font-medium">
          Biện pháp khắc phục
          {draft.kind === 'safety_relevant' ? ' (bắt buộc)' : ' (không bắt buộc)'}
        </label>
        <textarea
          id={`${idPrefix}-khac-phuc`}
          maxLength={4000}
          disabled={disabled}
          value={draft.mitigation}
          onChange={(event) => onChange({ ...draft, mitigation: event.target.value })}
          className="min-h-20 w-full rounded-lg border border-input bg-background px-3 py-2 text-base"
        />
      </div>
      {error && <FormAlert>{error}</FormAlert>}
      {'error' in check && !disabled && (
        <p className="text-sm text-muted-foreground">{check.error}</p>
      )}
      <Button
        className="min-h-12 w-full"
        disabled={disabled || saving || 'error' in check}
        onClick={onSave}
      >
        {saving ? 'Đang lưu…' : 'Lưu verdict (Ctrl+Enter)'}
      </Button>
    </div>
  )
}

export function ShortcutHelp({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogTitle>Phím tắt</DialogTitle>
        <DialogDescription className="sr-only">Phím tắt khi review failure case</DialogDescription>
        <ShortcutTable />
      </DialogContent>
    </Dialog>
  )
}

export function ShortcutTable() {
  return (
    <table className="w-full text-sm" data-testid="bang-phim-tat">
      <tbody>
        {SHORTCUTS.map(([keys, text]) => (
          <tr key={keys} className="border-t first:border-t-0">
            <td className="py-2 pr-3 font-mono whitespace-nowrap">{keys}</td>
            <td className="py-2">{text}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function History({ verdicts }: { verdicts: CaseVerdictView[] }) {
  if (verdicts.length === 0)
    return <p className="text-sm text-muted-foreground">Chưa có verdict.</p>
  return (
    <ol className="space-y-2 text-sm" data-testid="lich-su-verdict">
      {verdicts.map((v) => (
        <li key={v.version} className="rounded-lg bg-muted/50 p-2">
          <p className="font-medium">
            v{v.version}: {SEVERITY_LABEL[v.severity]}, {KIND_LABEL[v.kind]}
          </p>
          <p className="text-muted-foreground">
            {v.reviewer.full_name} · {formatDateTime(v.created_at)}
          </p>
          {v.mitigation && <p>{v.mitigation}</p>}
        </li>
      ))}
    </ol>
  )
}

/**
 * Route `/reviews/:id/cases/:caseId`: mỗi case một instance riêng (`key`), để bản nháp verdict,
 * lỗi lưu và bottom sheet của case trước không sang case sau khi chuyển bằng J/K hoặc vuốt.
 */
export function ReviewCaseRoute() {
  const { caseId = '' } = useParams()
  return <ReviewCasePage key={caseId} />
}

/**
 * Review một failure case (requirements.md Phase 8, Frontend reviewer; plan task 29): trình xem,
 * form verdict và lịch sử verdict; phím tắt trên desktop; vuốt và bottom sheet trên điện thoại.
 */
export function ReviewCasePage() {
  const { id = '', caseId = '' } = useParams()
  const navigate = useNavigate()
  const { data: me } = useMe()
  const experiment = useExperiment(id)
  const view = useFailureCase(caseId)
  const verdicts = useVerdicts(caseId)
  const add = useAddVerdict(id, caseId)
  const retry = useRetryOnImageError(() => view.refetch(), view.data?.urls_expire_at)
  const [draft, setDraft] = useState<VerdictDraft>(EMPTY)
  const [loadedFor, setLoadedFor] = useState<string | null>(null)
  const [help, setHelp] = useState(false)
  const [sheet, setSheet] = useState(false)

  // Điền sẵn verdict hiện hành (một lần cho mỗi case).
  if (verdicts.data && loadedFor !== caseId) {
    setLoadedFor(caseId)
    setDraft(draftOf(verdicts.data[0]))
  }

  const e = experiment.data
  // Chỉ người đang nhận review ghi verdict (server cũng kiểm: 403).
  const canWrite = e?.status === 'in_review' && me !== undefined && e.review?.assignee?.id === me.id
  // Chỉ ghi khi đã điền sẵn verdict hiện hành của đúng case này.
  const ready = loadedFor === caseId
  const nav = e ? neighbours(e, caseId) : { index: -1, total: 0, prev: undefined, next: undefined }
  const goTo = useCallback(
    (target: string | undefined) => {
      if (target) void navigate(`/reviews/${id}/cases/${target}`)
    },
    [navigate, id],
  )
  const save = useCallback(() => {
    const check = verdictBody(draft)
    if ('body' in check && canWrite && ready)
      add.mutate(check.body, { onSuccess: () => setSheet(false) })
  }, [draft, canWrite, ready, add])

  // Phím tắt: bỏ qua phím chữ khi đang gõ trong ô nhập (Ctrl+Enter vẫn lưu).
  const handler = useRef<(event: KeyboardEvent) => void>(() => undefined)
  const onKey = (event: KeyboardEvent) => {
    const action = shortcutOf({
      key: event.key,
      ctrlKey: event.ctrlKey,
      metaKey: event.metaKey,
      altKey: event.altKey,
      inField: isTextField(event.target),
    })
    if (!action) return
    event.preventDefault()
    if (action.type === 'help') setHelp(true)
    else if (action.type === 'next') goTo(nav.next)
    else if (action.type === 'prev') goTo(nav.prev)
    else if (action.type === 'save') save()
    else if (canWrite && ready) setDraft((d) => applyShortcut(d, action))
  }
  useEffect(() => {
    handler.current = onKey
  })
  useEffect(() => {
    const listener = (event: KeyboardEvent) => handler.current(event)
    window.addEventListener('keydown', listener)
    return () => window.removeEventListener('keydown', listener)
  }, [])

  if (view.isPending || experiment.isPending) return <PageLoading />
  if (view.isError || experiment.isError) {
    return (
      <div className="p-4 md:p-6">
        <LoadError
          onRetry={() => {
            void view.refetch()
            void experiment.refetch()
          }}
          retrying={view.isFetching || experiment.isFetching}
        />
      </div>
    )
  }
  const formProps = {
    draft,
    onChange: setDraft,
    onSave: save,
    saving: add.isPending,
    error: add.isError ? errorMessage(add.error) : null,
    disabled: !canWrite || !ready,
  }
  const aside = (
    <div className="space-y-4">
      {canWrite && !ready && (
        <p className="text-sm text-muted-foreground">
          {verdicts.isError
            ? 'Không tải được verdict hiện hành của case: chưa ghi được verdict.'
            : 'Đang tải verdict hiện hành…'}
        </p>
      )}
      {!canWrite && (
        <p className="text-sm text-muted-foreground">
          Chỉ người đang nhận review mới ghi verdict (experiment đang ở trạng thái{' '}
          {experiment.data.status}).
        </p>
      )}
      <div className="hidden md:block">
        <VerdictForm {...formProps} idPrefix="verdict" />
      </div>
      <Button variant="outline" className="hidden md:inline-flex" onClick={() => setHelp(true)}>
        <Keyboard aria-hidden="true" />
        Phím tắt (?)
      </Button>
      <section className="space-y-2" aria-label="Lịch sử verdict">
        <h2 className="font-medium">Lịch sử verdict</h2>
        {verdicts.isError ? (
          <LoadError onRetry={() => void verdicts.refetch()} retrying={verdicts.isFetching} />
        ) : (
          <History verdicts={verdicts.data ?? []} />
        )}
      </section>
    </div>
  )

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-4 p-4 pb-28 md:p-6">
      <header className="flex flex-col gap-1">
        <Link to={`/reviews/${id}`} className="text-sm text-muted-foreground hover:underline">
          ← Review {experiment.data.name}
        </Link>
        <h1 className="text-2xl font-semibold">Failure case {view.data.image_id}</h1>
        {nav.index >= 0 && (
          <p className="text-sm text-muted-foreground">
            Case bắt buộc {nav.index + 1}/{nav.total}
          </p>
        )}
      </header>
      <CaseViewer
        caseView={view.data}
        onPrev={nav.prev ? () => goTo(nav.prev) : undefined}
        onNext={nav.next ? () => goTo(nav.next) : undefined}
        onImageError={retry}
        aside={aside}
      />
      {/* Điện thoại: nút lớn mở form verdict trong bottom sheet. */}
      {canWrite && (
        <div className="fixed inset-x-0 bottom-[calc(3.5rem+1px+env(safe-area-inset-bottom))] z-30 border-t bg-background px-4 py-3 md:hidden">
          <Button className="min-h-12 w-full" onClick={() => setSheet(true)}>
            Ghi verdict
          </Button>
        </div>
      )}
      <Dialog open={sheet} onOpenChange={setSheet}>
        <DialogContent>
          <DialogTitle>Verdict cho ảnh {view.data.image_id}</DialogTitle>
          <DialogDescription className="sr-only">Form verdict</DialogDescription>
          <VerdictForm {...formProps} idPrefix="verdict-sheet" />
        </DialogContent>
      </Dialog>
      <ShortcutHelp open={help} onOpenChange={setHelp} />
    </div>
  )
}
