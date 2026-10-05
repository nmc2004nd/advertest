import { Check, ChevronLeft, ChevronRight, TriangleAlert, X } from 'lucide-react'
import { useEffect, useMemo, useReducer, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router'

import { ApiError } from '@/api/errors'
import { errorMessage } from '@/api/messages'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { FormAlert } from '@/components/FormAlert'
import { Button } from '@/components/ui/button'
import type { EstimateResponse } from '@/contracts/api'
import { GradientWaves } from '@/components/background/GradientWaves'
import { cn } from '@/lib/utils'

import {
  useAttackSpecs,
  useClassMappings,
  useClone,
  useComputeTargets,
  useCreateExperiment,
  useEstimate,
  useModels,
  useProtocol,
  useProtocols,
  useSlices,
} from './api'
import { COMPLIANCE_LABEL, requiredLocks } from './protocol'
import {
  buildBody,
  canAdvance,
  missingHint,
  clearDraft,
  type Draft,
  draftFromClone,
  estimateText,
  formatDuration,
  groupFieldErrors,
  hasLevelInputError,
  hasSearchInputError,
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
import { FloatingDecor } from '@/components/background/FloatingDecor'
import { WIZARD_DECOR } from '@/components/background/decor-presets'

/** Một câu hướng dẫn cho từng bước, hiện ngay dưới tiêu đề bước. */
const STEP_HINTS: Record<Step, string> = {
  1: 'Chọn protocol để hệ thống tự thêm attack bắt buộc và kiểm tra tuân thủ. Protocol dev chỉ để thử, không gửi duyệt được.',
  2: 'Chọn model cần kiểm định. Attack white-box cần model hỗ trợ gradient.',
  3: 'Chọn dataset và slice ảnh. Slice phải đủ lớn theo protocol mới gửi duyệt được.',
  4: 'Bật attack và chọn level, hoặc để hệ thống tự tìm ngưỡng gãy. Ước lượng thời gian cập nhật ngay bên phải.',
  5: 'Chọn máy chạy và giới hạn thời gian. Chạm giới hạn thì experiment dừng và giữ kết quả đã có.',
  6: 'Kiểm tra lại cấu hình và ước lượng rồi bấm chạy. Kết quả là bản nháp cho tới khi được duyệt.',
}

function StepBar({ draft, onGo }: { draft: Draft; onGo: (step: Step) => void }) {
  const current = STEPS[draft.step - 1]
  return (
    <nav aria-label="Các bước">
      <div className="flex flex-col gap-2 md:hidden">
        <p className="text-sm text-muted-foreground">
          Bước {draft.step}/6: <span className="font-medium text-foreground">{current.title}</span>
        </p>
        <div className="flex gap-1" aria-hidden>
          {STEPS.map(({ step }) => (
            <span
              key={step}
              className={cn(
                'h-1 flex-1 rounded-full',
                step <= draft.step
                  ? 'bg-gradient-to-r from-[#2563eb] via-[#7c3aed] to-[#ec4899] bg-fixed'
                  : 'bg-secondary',
              )}
            />
          ))}
        </div>
      </div>
      <ol className="hidden items-center gap-1 md:flex">
        {STEPS.map(({ step, title }) => {
          const done = step < draft.step
          const here = step === draft.step
          return (
            <li key={step} className="flex min-w-0 flex-1 items-center gap-1">
              <button
                type="button"
                disabled={step > draft.step}
                aria-current={here ? 'step' : undefined}
                onClick={() => onGo(step)}
                className={cn(
                  'flex min-h-11 min-w-0 items-center gap-2 rounded-lg px-1.5 text-left text-[13.5px] transition-colors focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none',
                  here && 'font-semibold text-foreground',
                  done && 'text-foreground hover:bg-muted',
                  step > draft.step && 'text-muted-foreground',
                )}
              >
                <span
                  className={cn(
                    'flex size-7 shrink-0 items-center justify-center rounded-full text-[12.5px] font-semibold tabular-nums transition-all duration-300',
                    done && 'bg-navy text-primary-foreground',
                    here &&
                      'border-2 border-navy bg-surface-solid text-foreground ring-4 ring-violet/15',
                    !done && !here && 'border-2 border-line text-muted-foreground',
                  )}
                >
                  {done ? <Check className="size-3.5" aria-hidden="true" /> : step}
                </span>
                <span className="leading-tight">{title}</span>
              </button>
              {step < 6 && (
                <span
                  aria-hidden
                  className={cn(
                    'h-0.5 min-w-3 flex-1 rounded-full',
                    done ? 'bg-gradient-to-r from-[#2563eb] to-[#7c3aed]' : 'bg-line',
                  )}
                />
              )}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}

function EstimateWarnings({ estimate }: { estimate: EstimateResponse | undefined }) {
  if (!estimate) return null
  return (
    <>
      {estimate.exceeds_limit && (
        <p role="alert" className="flex gap-2 text-sm text-threshold">
          <TriangleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
          Ước lượng vượt giới hạn thời gian: experiment có thể dừng giữa chừng (giữ kết quả một
          phần).
        </p>
      )}
      {estimate.max_exceeds_limit && (
        <p role="alert" className="flex gap-2 text-sm text-threshold">
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
    <div className="space-y-4 text-sm">
      <dl>
        {rows.map(([label, value]) => (
          <div
            key={label}
            className="flex justify-between gap-3 border-b border-line py-2.5 text-[13px]"
          >
            <dt className="shrink-0 text-muted-foreground">{label}</dt>
            <dd
              className={cn(
                'min-w-0 truncate text-right',
                value === '—' ? 'text-muted-foreground' : 'font-medium text-foreground',
              )}
              title={value}
            >
              {value}
            </dd>
          </div>
        ))}
      </dl>
      <div>
        <p className="mb-1 text-[13px] text-muted-foreground">Attack</p>
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
      <div className="flex items-end justify-between gap-3 border-y border-line py-4">
        <span className="text-[13px] text-muted-foreground">
          Thời gian ước lượng
          {estimating && <span className="block text-detect-strong">đang tính…</span>}
        </span>
        <strong className="text-xl leading-none font-semibold tabular-nums">
          {estimateText(estimate)}
        </strong>
      </div>
      <div>
        {estimate && (
          <p className="text-muted-foreground">
            Vị trí hàng đợi: {estimate.queue.position} · chờ khoảng{' '}
            {formatDuration(estimate.queue.ahead_seconds || null)}
          </p>
        )}
      </div>
      <EstimateWarnings estimate={estimate} />
      <ComplianceTable estimate={estimate} />
    </div>
  )
}

/** Phase 8: tuân thủ protocol (từ ước lượng), ✓/✗ kèm lý do. */
function ComplianceTable({ estimate }: { estimate: EstimateResponse | undefined }) {
  const items = estimate?.compliance ?? []
  if (items.length === 0) return null
  const failing = items.filter((item) => !item.satisfied).length
  return (
    <div className="space-y-1" data-testid="bang-tuan-thu">
      <p className="font-medium">
        Tuân thủ protocol:{' '}
        {failing === 0 ? 'đủ' : <span className="text-destructive">{failing} mục chưa thỏa</span>}
      </p>
      <ul className="space-y-1">
        {items.map((item, i) => (
          <li key={i} className="flex gap-2">
            {item.satisfied ? (
              <Check aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-approved" />
            ) : (
              <X aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-destructive" />
            )}
            <span>
              <span className="sr-only">{item.satisfied ? 'Đạt: ' : 'Chưa đạt: '}</span>
              {COMPLIANCE_LABEL[item.code]}
              {item.attack_spec_name ? ` (${item.attack_spec_name})` : ''}:{' '}
              <span className="text-muted-foreground">{item.detail}</span>
            </span>
          </li>
        ))}
      </ul>
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
          className="space-y-1 rounded-[10px] bg-threshold/10 p-3 text-sm text-threshold shadow-[inset_0_0_0_1px_color-mix(in_oklab,var(--threshold)_35%,transparent)]"
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
          className="min-h-11 rounded-[10px] border border-input bg-field px-3.5 text-base text-foreground shadow-[0_1px_2px_rgba(16,24,40,0.05)] outline-none transition-[border-color,box-shadow] duration-200 placeholder:text-muted-foreground/70 hover:border-muted-foreground focus-visible:border-violet focus-visible:ring-4 focus-visible:ring-violet/15"
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
  const protocol = useProtocol(draft.protocolId)
  const specs = useAttackSpecs()
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

  // Phase 8: tải xong protocol thì thêm và khóa attack bắt buộc (cả khi nhân bản).
  useEffect(() => {
    const view = protocol.data
    if (!view || !specs.data || view.id !== draft.protocolId) return
    if (draft.requiredFor === view.id) return
    dispatch({
      type: 'requirements',
      protocolId: view.id,
      locks: requiredLocks(view.body, specs.data).locks,
      minSliceSize: view.body.min_slice_size,
    })
  }, [protocol.data, specs.data, draft.protocolId, draft.requiredFor])

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
  // Form tìm ngưỡng còn lỗi thì chưa ước lượng: API chỉ trả 422 (review Group 5 #1).
  const searchInputError = hasSearchInputError(draft.attacks, levelInputErrors)
  const estimate = useEstimate(draft.step >= 4 && !searchInputError ? estimateBody : null)
  const target = targets.data?.find((t) => t.id === draft.targetId)
  const model = models.data?.find((m) => m.id === draft.modelId)
  const levelInputError = hasLevelInputError(draft.attacks, levelInputErrors)
  const counts = runCounts(draft, estimate.data)
  const advance = canAdvance(draft, {
    maxLimitSeconds: target?.max_time_limit_s,
    levelInputError,
  })
  const missing = missingHint(draft, {
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
    <div className="mx-auto flex max-w-7xl flex-col gap-6 p-4 pb-24 md:p-8">
      {/* Dải cảnh lụa 3D phía trên, thanh bước nằm trong thẻ trắng đè lên mép dưới (giống màn hình
          onboarding của beehiiv). Lớp phủ tối bên trái giữ chữ trắng đủ tương phản. */}
      <div className="relative isolate -mb-20 overflow-hidden rounded-[20px] px-6 pt-7 pb-28 text-white md:px-9 md:pt-9">
        <GradientWaves className="absolute inset-0 -z-10" scale={0.7} />
        <div
          aria-hidden
          className="absolute inset-0 -z-10 bg-gradient-to-r from-[#1e1b4b]/80 via-[#1e1b4b]/40 to-transparent"
        />
        <FloatingDecor items={WIZARD_DECOR} className="hidden md:block" />
        <h1 className="text-[clamp(1.85rem,2.6vw,2.5rem)] leading-[1.1] font-bold tracking-[-0.035em]">
          Tạo experiment
        </h1>
        <p className="mt-2 max-w-[60ch] text-[15px] leading-6 text-white/85">
          Sáu bước: chọn protocol, model, ảnh và attack. Nháp được lưu tự động trên trình duyệt này;
          rời trang rồi quay lại vẫn còn.
        </p>
      </div>
      <div className="panel relative z-10 mx-3 px-3 py-2 md:mx-6">
        <StepBar draft={draft} onGo={go} />
      </div>
      {cloneId !== null && cloneFailed && (
        <FormAlert>Không tải được cấu hình để nhân bản.</FormAlert>
      )}
      {create.isError && (
        <FormAlert>
          {create.error instanceof ApiError && create.error.code === 'queue_limit_reached'
            ? `${errorMessage(create.error)} Cấu hình của bạn vẫn được giữ.`
            : create.error instanceof ApiError && create.error.code === 'not_compliant'
              ? `${errorMessage(create.error)} Xem bảng tuân thủ trong phần tóm tắt.`
              : errorMessage(create.error)}
        </FormAlert>
      )}
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_21rem]">
        <section aria-labelledby="tieu-de-buoc" className="panel min-w-0 space-y-5 p-5 md:p-6">
          <div className="flex flex-col gap-1.5 border-b border-line pb-4">
            <p className="self-start rounded-full bg-violet-soft px-2.5 py-0.5 text-[12.5px] font-semibold text-[#6d28d9] dark:text-violet">
              Bước {draft.step} trên 6
            </p>
            <h2 id="tieu-de-buoc" className="text-xl font-semibold">
              {STEPS[draft.step - 1].title}
            </h2>
            <p className="max-w-[72ch] text-sm text-muted-foreground">{STEP_HINTS[draft.step]}</p>
          </div>
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
          <div className="hidden items-center gap-3 border-t border-line pt-5 md:flex">
            <Button
              variant="ghost"
              onClick={() => go((draft.step - 1) as Step)}
              disabled={draft.step === 1}
            >
              <ChevronLeft aria-hidden="true" />
              Lùi
            </Button>
            {draft.step < 6 && !advance && (
              <p className="ml-auto text-right text-sm text-muted-foreground">{missing}</p>
            )}
            {draft.step < 6 ? (
              <Button onClick={next} disabled={!advance} className={cn(advance && 'ml-auto')}>
                Tiếp: {STEPS[draft.step as 1 | 2 | 3 | 4 | 5].title}
                <ChevronRight aria-hidden="true" />
              </Button>
            ) : (
              <Button
                size="lg"
                className="ml-auto"
                onClick={() => setConfirming(true)}
                disabled={!body || create.isPending}
              >
                Chạy experiment
              </Button>
            )}
          </div>
        </section>
        <aside className="hidden lg:block" aria-label="Tóm tắt cấu hình">
          <div className="panel sticky top-6 overflow-hidden p-5 pt-6">
            <span
              aria-hidden
              className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-[#2563eb] via-[#7c3aed] to-[#ec4899]"
            />
            <h2 className="font-semibold">Bạn đang cấu hình</h2>
            <p className="mb-2 text-sm text-muted-foreground">
              Cập nhật theo từng lựa chọn. Chưa có gì được chạy cho tới khi bạn bấm "Chạy
              experiment".
            </p>
            <Summary draft={draft} estimate={estimate.data} estimating={estimate.isFetching} />
          </div>
        </aside>
      </div>
      {/* Điện thoại: thanh dưới cố định (thời gian ước lượng + nút), nằm ngay trên thanh tab điều
          hướng của khung ứng dụng (cao 3.5rem + viền, đã tránh thanh home). */}
      <div className="fixed inset-x-0 bottom-[calc(3.5rem+1px+env(safe-area-inset-bottom))] z-30 border-t border-line bg-background/95 px-4 py-3 backdrop-blur-xl md:hidden">
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
