import { ChevronLeft, ChevronRight, TriangleAlert } from 'lucide-react'
import { useEffect, useMemo, useReducer, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router'

import { ApiError } from '@/api/errors'
import { errorMessage } from '@/api/messages'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { FormAlert } from '@/components/FormAlert'
import { Button } from '@/components/ui/button'
import type { EstimateResponse } from '@/contracts/api'
import { cn } from '@/lib/utils'

import {
  useAttackSpecs,
  useClassMappings,
  useClone,
  useComputeTargets,
  useCreateExperiment,
  useEstimate,
  useModels,
  useProtocols,
  useSlices,
} from './api'
import {
  buildBody,
  canAdvance,
  clearDraft,
  type Draft,
  draftFromClone,
  estimateText,
  formatDuration,
  groupFieldErrors,
  hasLevelInputError,
  loadDraft,
  reducer,
  runCounts,
  saveDraft,
  searchCostSummary,
  SEED,
  type Step,
  STEPS,
} from './state'
import { AttackStep, DatasetStep, ModelStep, ProtocolStep, TargetStep } from './steps'

function StepBar({ draft, onGo }: { draft: Draft; onGo: (step: Step) => void }) {
  const current = STEPS[draft.step - 1]
  return (
    <nav aria-label="Các bước">
      <p className="text-sm text-muted-foreground md:hidden">
        Bước {draft.step}/6: <span className="font-medium text-foreground">{current.title}</span>
      </p>
      <ol className="hidden gap-1 md:flex">
        {STEPS.map(({ step, title }) => (
          <li key={step} className="flex-1">
            <button
              type="button"
              disabled={step > draft.step}
              aria-current={step === draft.step ? 'step' : undefined}
              onClick={() => onGo(step)}
              className={cn(
                'flex min-h-11 w-full items-center gap-2 rounded-lg border px-2 text-left text-sm',
                step === draft.step
                  ? 'border-primary bg-primary/5 font-medium'
                  : 'text-muted-foreground',
                step > draft.step && 'opacity-50',
              )}
            >
              <span className="tabular-nums">{step}</span>
              <span className="truncate">{title}</span>
            </button>
          </li>
        ))}
      </ol>
    </nav>
  )
}

function EstimateWarnings({ estimate }: { estimate: EstimateResponse | undefined }) {
  if (!estimate) return null
  return (
    <>
      {estimate.exceeds_limit && (
        <p role="alert" className="flex gap-2 text-sm text-amber-800 dark:text-amber-300">
          <TriangleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
          Ước lượng vượt giới hạn thời gian: experiment có thể dừng giữa chừng (giữ kết quả một
          phần).
        </p>
      )}
      {estimate.max_exceeds_limit && (
        <p role="alert" className="flex gap-2 text-sm text-amber-800 dark:text-amber-300">
          <TriangleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
          Chi phí tối đa của tìm ngưỡng vượt giới hạn thời gian: nếu chạm giới hạn, kết quả tìm
          ngưỡng dừng ở khoảng đã thu hẹp được.
        </p>
      )}
      {estimate.missing_profiles.length > 0 && (
        <p className="flex gap-2 text-sm text-muted-foreground">
          <TriangleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
          Chưa có số đo tốc độ cho {estimate.missing_profiles.length} attack trên máy này: worker sẽ
          tự đo, chưa ước lượng được tổng thời gian.
        </p>
      )}
    </>
  )
}

/** Tóm tắt cấu hình (cột phải trên desktop, nội dung bước 6). */
function Summary({
  draft,
  estimate,
  estimating,
}: {
  draft: Draft
  estimate: EstimateResponse | undefined
  estimating: boolean
}) {
  const protocols = useProtocols()
  const models = useModels()
  const slices = useSlices(draft.datasetVersionId)
  const specs = useAttackSpecs()
  const targets = useComputeTargets()
  const name = <T extends { id: string; name: string }>(
    items: T[] | undefined,
    id: string | null,
  ) => items?.find((item) => item.id === id)?.name ?? '—'
  const rows: [string, string][] = [
    ['Protocol', name(protocols.data, draft.protocolId)],
    ['Model', name(models.data, draft.modelId)],
    ['Slice', name(slices.data, draft.sliceId)],
    ['Máy chạy', name(targets.data, draft.targetId)],
    ['Giới hạn', formatDuration(draft.limitSeconds)],
    ['Seed', String(SEED)],
  ]
  return (
    <div className="space-y-3 text-sm">
      <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1">
        {rows.map(([label, value]) => (
          <div key={label} className="contents">
            <dt className="text-muted-foreground">{label}</dt>
            <dd className="break-all">{value}</dd>
          </div>
        ))}
      </dl>
      <div>
        <p className="text-muted-foreground">Attack</p>
        {draft.attacks.length === 0 ? (
          <p>—</p>
        ) : (
          <ul>
            {draft.attacks.map((a) => (
              <li key={a.attackSpecId}>
                {name(specs.data, a.attackSpecId)}:{' '}
                {a.mode === 'search' ? 'tự tìm ngưỡng' : a.levels.join(', ') || 'chưa có level'}
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="rounded-lg bg-muted p-3">
        <p>
          Ước lượng: <strong>{estimateText(estimate)}</strong>
          {estimating && <span className="text-muted-foreground"> (đang tính)</span>}
        </p>
        {estimate && (
          <p className="text-muted-foreground">
            Vị trí hàng đợi: {estimate.queue.position} · chờ khoảng{' '}
            {formatDuration(estimate.queue.ahead_seconds || null)}
          </p>
        )}
      </div>
      <EstimateWarnings estimate={estimate} />
    </div>
  )
}

function ConfirmStep({
  draft,
  estimate,
  estimating,
  errors,
  onName,
}: {
  draft: Draft
  estimate: EstimateResponse | undefined
  estimating: boolean
  errors: Record<string, string>
  onName: (name: string) => void
}) {
  const specs = useAttackSpecs()
  return (
    <div className="space-y-4">
      {draft.cloneWarnings.length > 0 && (
        <div
          role="alert"
          className="space-y-1 rounded-lg bg-amber-100 p-3 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-200"
        >
          {draft.cloneWarnings.map((w) => (
            <p key={w.attack_spec_id}>{w.message}</p>
          ))}
        </div>
      )}
      <div className="flex max-w-md flex-col gap-1.5">
        <label htmlFor="ten-experiment" className="text-sm font-medium">
          Tên experiment (không bắt buộc)
        </label>
        <input
          id="ten-experiment"
          value={draft.name}
          maxLength={200}
          onChange={(event) => onName(event.target.value)}
          className="min-h-11 rounded-lg border border-input bg-background px-3 text-base"
        />
        <p className="text-sm text-muted-foreground">
          Bỏ trống: hệ thống đặt theo model, slice và ngày.
        </p>
        {errors.name && (
          <p role="alert" className="text-sm text-destructive">
            {errors.name}
          </p>
        )}
      </div>
      <div className="lg:hidden">
        <Summary draft={draft} estimate={estimate} estimating={estimating} />
      </div>
      {estimate && (estimate.searches ?? []).length > 0 && (
        <div className="space-y-1 text-sm" data-testid="chi-phi-tim-nguong">
          <p className="font-medium">Chi phí tối đa của tìm ngưỡng</p>
          <ul>
            {(estimate.searches ?? []).map((s) => (
              <li key={s.attack_spec_id}>
                {specs.data?.find((spec) => spec.id === s.attack_spec_id)?.name ?? '—'}:{' '}
                {searchCostSummary(estimate, s.attack_spec_id)}
              </li>
            ))}
          </ul>
          <p className="text-muted-foreground">
            Tìm ngưỡng thường dừng sớm hơn mức tối đa khi khoảng đã đủ hẹp.
          </p>
        </div>
      )}
      {estimate && estimate.runs.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[22rem] text-sm">
            <caption className="text-left font-medium">Ước lượng từng run</caption>
            <thead className="text-left text-muted-foreground">
              <tr>
                <th scope="col" className="py-1 pr-3 font-medium">
                  Attack
                </th>
                <th scope="col" className="py-1 pr-3 font-medium">
                  Level
                </th>
                <th scope="col" className="py-1 pr-3 font-medium">
                  Ảnh
                </th>
                <th scope="col" className="py-1 pr-3 font-medium">
                  Thời gian
                </th>
                <th scope="col" className="py-1 font-medium">
                  Train patch
                </th>
              </tr>
            </thead>
            <tbody>
              {estimate.runs.map((run) => (
                <tr key={`${run.attack_spec_id}-${run.level}`} className="border-t">
                  <td className="py-1 pr-3">
                    {specs.data?.find((s) => s.id === run.attack_spec_id)?.name ?? '—'}
                  </td>
                  <td className="py-1 pr-3 tabular-nums">{run.level}</td>
                  <td className="py-1 pr-3 tabular-nums">{run.images}</td>
                  <td className="py-1 pr-3">
                    {run.skip_reason === 'incompatible'
                      ? 'Sẽ bỏ qua (model không hỗ trợ gradient)'
                      : formatDuration(run.est_seconds)}
                  </td>
                  <td className="py-1">{formatDuration(run.training_seconds)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="text-sm text-muted-foreground">
        Kết quả là bản nháp, chưa được duyệt. Protocol dev không gửi duyệt được.
      </p>
    </div>
  )
}

/** Wizard tạo experiment 6 bước (`/experiments/new`, `?clone=<id>` để nhân bản). */
export function WizardPage() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const cloneId = params.get('clone')
  const [draft, dispatch] = useReducer(reducer, undefined, loadDraft)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [levelInputErrors, setLevelInputErrors] = useState<Record<string, boolean>>({})
  const [confirming, setConfirming] = useState(false)

  const protocols = useProtocols()
  const models = useModels()
  const targets = useComputeTargets()
  const mappings = useClassMappings(draft.datasetVersionId, draft.modelId)
  const clone = useClone(cloneId)
  const allSlices = useSlices(null, cloneId !== null)
  const create = useCreateExperiment()

  useEffect(() => saveDraft(draft), [draft])

  // Nhân bản: điền sẵn và mở bước 6 (một lần cho mỗi experiment gốc).
  useEffect(() => {
    if (!clone.data || !allSlices.data || draft.clonedFrom === cloneId) return
    const slice = allSlices.data.find((s) => s.id === clone.data.config.slice_id)
    dispatch({
      type: 'load',
      draft: draftFromClone(
        clone.data.config,
        clone.data.warnings,
        slice?.dataset_version_id ?? null,
      ),
    })
  }, [clone.data, allSlices.data, cloneId, draft.clonedFrom])

  // Chọn sẵn khi chỉ có một lựa chọn, và máy local (ưu tiên online) để ước lượng từ bước 4.
  useEffect(() => {
    if (!draft.protocolId && protocols.data?.length === 1) {
      dispatch({ type: 'protocol', id: protocols.data[0].id })
    }
  }, [draft.protocolId, protocols.data])
  useEffect(() => {
    if (draft.targetId || !targets.data) return
    const local = targets.data.filter((t) => t.kind === 'local')
    const pick = local.find((t) => t.online) ?? local[0]
    if (pick)
      dispatch({ type: 'target', id: pick.id, defaultLimitSeconds: pick.default_time_limit_s })
  }, [draft.targetId, targets.data])
  useEffect(() => {
    const list = mappings.data
    if (!list) return
    if (list.length === 1 && draft.mappingId !== list[0].id) {
      dispatch({ type: 'mapping', id: list[0].id })
    } else if (
      list.length !== 1 &&
      draft.mappingId &&
      !list.some((m) => m.id === draft.mappingId)
    ) {
      dispatch({ type: 'mapping', id: null })
    }
  }, [mappings.data, draft.mappingId])

  const body = useMemo(() => buildBody(draft), [draft])
  // Tên không ảnh hưởng ước lượng: bỏ khỏi body để gõ tên không gọi lại API.
  const estimateBody = useMemo(() => (body ? { ...body, name: null } : null), [body])
  const estimate = useEstimate(draft.step >= 4 ? estimateBody : null)
  const target = targets.data?.find((t) => t.id === draft.targetId)
  const model = models.data?.find((m) => m.id === draft.modelId)
  const levelInputError = hasLevelInputError(draft.attacks, levelInputErrors)
  const counts = runCounts(draft, estimate.data)
  const advance = canAdvance(draft, {
    maxLimitSeconds: target?.max_time_limit_s,
    levelInputError,
  })

  const go = (step: Step) => dispatch({ type: 'go', step })
  const next = () => {
    if (draft.step < 6 && advance) go((draft.step + 1) as Step)
  }

  const submit = () => {
    if (!body) return
    setErrors({})
    create.mutate(body, {
      onSuccess: (experiment) => {
        clearDraft()
        void navigate(`/experiments/${experiment.id}`)
      },
      onError: (error) => {
        setConfirming(false)
        if (error instanceof ApiError && error.fields.length > 0) {
          const grouped = groupFieldErrors(error.fields)
          setErrors(grouped.byPath)
          if (grouped.firstStep) go(grouped.firstStep)
        }
      },
    })
  }

  const stepProps = { draft, dispatch, errors }
  const cloneFailed = clone.isError || allSlices.isError
  const loadingClone = cloneId !== null && draft.clonedFrom !== cloneId && !cloneFailed
  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-4 p-4 pb-24 md:p-6">
      <h1 className="text-2xl font-semibold">Tạo experiment</h1>
      <StepBar draft={draft} onGo={go} />
      {cloneId !== null && cloneFailed && (
        <FormAlert>Không tải được cấu hình để nhân bản.</FormAlert>
      )}
      {create.isError && (
        <FormAlert>
          {create.error instanceof ApiError && create.error.code === 'queue_limit_reached'
            ? `${errorMessage(create.error)} Cấu hình của bạn vẫn được giữ.`
            : errorMessage(create.error)}
        </FormAlert>
      )}
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <section aria-labelledby="tieu-de-buoc" className="min-w-0 space-y-4">
          <h2 id="tieu-de-buoc" className="text-lg font-semibold">
            {STEPS[draft.step - 1].title}
          </h2>
          {loadingClone ? (
            <p className="text-muted-foreground">Đang tải cấu hình để nhân bản…</p>
          ) : (
            <>
              {draft.step === 1 && <ProtocolStep {...stepProps} />}
              {draft.step === 2 && <ModelStep {...stepProps} />}
              {draft.step === 3 && <DatasetStep {...stepProps} />}
              {draft.step === 4 && (
                <AttackStep
                  {...stepProps}
                  model={model}
                  estimate={estimate.data}
                  onLevelInputError={(id, bad) =>
                    setLevelInputErrors((current) => ({ ...current, [id]: bad }))
                  }
                />
              )}
              {draft.step === 5 && <TargetStep {...stepProps} estimate={estimate.data} />}
              {draft.step === 6 && (
                <ConfirmStep
                  draft={draft}
                  estimate={estimate.data}
                  estimating={estimate.isFetching}
                  errors={errors}
                  onName={(name) => dispatch({ type: 'name', name })}
                />
              )}
            </>
          )}
          {estimate.isError && draft.step >= 4 && (
            <p className="text-sm text-muted-foreground">
              Chưa ước lượng được: {errorMessage(estimate.error)}
            </p>
          )}
          {/* Desktop: nút điều hướng ngay dưới nội dung bước. */}
          <div className="hidden gap-2 md:flex">
            <Button
              variant="outline"
              onClick={() => go((draft.step - 1) as Step)}
              disabled={draft.step === 1}
            >
              <ChevronLeft aria-hidden="true" />
              Lùi
            </Button>
            {draft.step < 6 ? (
              <Button onClick={next} disabled={!advance}>
                Tiếp
                <ChevronRight aria-hidden="true" />
              </Button>
            ) : (
              <Button onClick={() => setConfirming(true)} disabled={!body || create.isPending}>
                Chạy experiment
              </Button>
            )}
          </div>
        </section>
        <aside className="hidden lg:block" aria-label="Tóm tắt cấu hình">
          <div className="sticky top-4 rounded-lg border p-4">
            <h2 className="mb-3 font-semibold">Tóm tắt</h2>
            <Summary draft={draft} estimate={estimate.data} estimating={estimate.isFetching} />
          </div>
        </aside>
      </div>
      {/* Điện thoại: thanh dưới cố định (thời gian ước lượng + nút), nằm ngay trên thanh tab điều
          hướng của khung ứng dụng (cao 3.5rem + viền, đã tránh thanh home). */}
      <div className="fixed inset-x-0 bottom-[calc(3.5rem+1px+env(safe-area-inset-bottom))] z-30 border-t bg-background px-4 py-3 md:hidden">
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            aria-label="Lùi"
            onClick={() => go((draft.step - 1) as Step)}
            disabled={draft.step === 1}
          >
            <ChevronLeft aria-hidden="true" />
          </Button>
          <p className="min-w-0 flex-1 truncate text-sm" data-testid="uoc-luong-thanh-duoi">
            Ước lượng: <strong>{estimateText(estimate.data)}</strong>
          </p>
          {draft.step < 6 ? (
            <Button onClick={next} disabled={!advance}>
              Tiếp
              <ChevronRight aria-hidden="true" />
            </Button>
          ) : (
            <Button onClick={() => setConfirming(true)} disabled={!body || create.isPending}>
              Chạy
            </Button>
          )}
        </div>
      </div>
      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title="Chạy experiment?"
        confirmLabel="Chạy experiment"
        pending={create.isPending}
        onConfirm={submit}
      >
        <div className="space-y-2 text-sm">
          <p>
            {counts.grid} run quét lưới
            {counts.maxPoints > 0 && ` · tìm ngưỡng tối đa ${counts.maxPoints} điểm`} · ước lượng{' '}
            {estimateText(estimate.data)} · giới hạn {formatDuration(draft.limitSeconds)}
          </p>
          <EstimateWarnings estimate={estimate.data} />
        </div>
      </ConfirmDialog>
    </div>
  )
}
