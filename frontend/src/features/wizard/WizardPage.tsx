import { Check, ChevronLeft, ChevronRight, TriangleAlert, X } from 'lucide-react'
import { useCallback, useEffect, useMemo, useReducer, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router'

import { ApiError } from '@/api/errors'
import { errorMessage } from '@/api/messages'
import { FormAlert } from '@/components/FormAlert'
import { Button } from '@/components/ui/button'
import type { EstimateResponse, ExperimentClone } from '@/contracts/api'
import { STEP_THREE_HINT, STEP_TWO_HINT, WIZARD_INTRO } from '@/copy/wizard'
import { GradientWaves } from '@/components/background/GradientWaves'
import { cn } from '@/lib/utils'

import {
  useAttackSpecs,
  useClassMappings,
  useClone,
  useComputeTargets,
  useCreateExperiment,
  useDraft,
  useEstimate,
  useModels,
  usePresets,
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
  draftKeyOf,
  draftRequest,
  estimateText,
  formatDuration,
  groupFieldErrors,
  hasLevelInputError,
  hasSearchInputError,
  LAST_STEP,
  loadDraft,
  reducer,
  saveDraft,
  searchCostSummary,
  SEED,
  type Step,
  STEPS,
} from './state'
import { specTitle } from './levels'
import { AttackStep, DataStep, PurposeStep } from './steps'
import { FloatingDecor } from '@/components/background/FloatingDecor'
import { WIZARD_DECOR } from '@/components/background/decor-presets'

/** Một câu hướng dẫn cho từng bước, hiện ngay dưới tiêu đề bước. */
const STEP_HINTS: Record<Step, string | null> = {
  1: null, // bước 1 có đoạn giới thiệu kèm thuật ngữ (PurposeStep)
  2: STEP_TWO_HINT,
  3: STEP_THREE_HINT,
}

/** Thanh bước (Phase R3: 3 bước). Phần tử `wizard-step` chỉ chứa tên bước; số thứ tự vẽ bằng CSS. */
function StepBar({ draft, onGo }: { draft: Draft; onGo: (step: Step) => void }) {
  return (
    <nav aria-label="Các bước">
      <ol className="flex items-center gap-1">
        {STEPS.map(({ step, title }) => {
          const done = step < draft.step
          const here = step === draft.step
          return (
            <li key={step} className="flex min-w-0 flex-1 items-center gap-1">
              <span
                aria-hidden
                data-n={step}
                className={cn(
                  'flex size-7 shrink-0 items-center justify-center rounded-full text-[12.5px] font-semibold tabular-nums transition-all duration-300',
                  done && 'bg-navy text-primary-foreground',
                  here &&
                    'border-2 border-navy bg-surface-solid text-foreground ring-4 ring-violet/15',
                  !done && !here && 'border-2 border-line text-muted-foreground',
                  !done && 'before:content-[attr(data-n)]',
                )}
              >
                {done && <Check className="size-3.5" />}
              </span>
              <button
                type="button"
                data-testid="wizard-step"
                disabled={step > draft.step}
                aria-current={here ? 'step' : undefined}
                onClick={() => onGo(step)}
                className={cn(
                  'flex min-h-11 min-w-0 items-center rounded-lg px-1.5 text-left text-[13px] leading-tight transition-colors focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none md:text-[13.5px]',
                  here && 'font-semibold text-foreground',
                  done && 'text-foreground hover:bg-muted',
                  step > draft.step && 'text-muted-foreground',
                )}
              >
                {title}
              </button>
              {step < LAST_STEP && (
                <span
                  aria-hidden
                  className={cn(
                    'hidden h-0.5 min-w-3 flex-1 rounded-full sm:block',
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

/** Tóm tắt cấu hình (cột phải trên desktop; trong bước 3 trên màn hình nhỏ). */
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
  const presets = usePresets()
  const models = useModels()
  const slices = useSlices(draft.datasetVersionId)
  const specs = useAttackSpecs()
  const targets = useComputeTargets()
  const name = <T extends { id: string; name: string }>(
    items: T[] | undefined,
    id: string | null,
  ) => items?.find((item) => item.id === id)?.name ?? '—'
  const rows: [string, string][] = [
    ['Mode', draft.mode === 'official' ? 'Chính thức' : 'Khám phá'],
    ['Protocol', name(protocols.data, draft.protocolId)],
    ['Preset', presets.data?.find((p) => p.key === draft.preset)?.title ?? '—'],
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
                {specTitle(specs.data?.find((spec) => spec.id === a.attackSpecId))}:{' '}
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

/** Phần xác nhận của bước 3: tên, lưu ý của bản nháp, ước lượng từng run. */
function ConfirmSection({
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
  const specName = (id: string) => specTitle(specs.data?.find((spec) => spec.id === id))
  return (
    <div className="space-y-4 border-t border-line pt-5">
      {draft.notes.length > 0 && (
        <div role="alert" className="space-y-1 text-sm text-threshold" data-testid="draft-notes">
          {draft.notes.map((note) => (
            <p key={note.code} className="flex gap-2">
              <TriangleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
              {note.message}
            </p>
          ))}
        </div>
      )}
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
                {specName(s.attack_spec_id)}: {searchCostSummary(estimate, s.attack_spec_id)}
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
                  <td className="py-1 pr-3">{specName(run.attack_spec_id)}</td>
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
        {draft.mode === 'exploration'
          ? 'Experiment Khám phá không gửi duyệt được; muốn có report thì nâng lên chính thức sau khi chạy xong.'
          : 'Kết quả là bản nháp cho tới khi reviewer duyệt.'}
      </p>
    </div>
  )
}

/** Wizard tạo experiment 3 bước (`/experiments/new`; `?clone=<id>` để nhân bản; nâng lên chính thức
 * lưu sẵn nháp rồi mở trang này ở bước 3). */
export function WizardPage() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const cloneId = params.get('clone')
  const [draft, dispatch] = useReducer(reducer, undefined, loadDraft)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [levelInputErrors, setLevelInputErrors] = useState<Record<string, boolean>>({})

  const protocols = useProtocols()
  const models = useModels()
  const targets = useComputeTargets()
  const mappings = useClassMappings(draft.datasetVersionId, draft.modelId)
  const clone = useClone(cloneId)
  const protocol = useProtocol(draft.protocolId)
  const specs = useAttackSpecs()
  const allSlices = useSlices(null, cloneId !== null)
  const create = useCreateExperiment()
  const drafting = useDraft()

  useEffect(() => saveDraft(draft), [draft])

  // Nhân bản: điền sẵn và mở bước 3 (một lần cho mỗi experiment gốc).
  useEffect(() => {
    if (!clone.data || !allSlices.data || !protocols.data || draft.clonedFrom === cloneId) return
    const slice = allSlices.data.find((s) => s.id === clone.data.config.slice_id)
    const source = protocols.data.find((p) => p.id === clone.data.config.protocol_id)
    dispatch({
      type: 'load',
      draft: draftFromClone(
        clone.data.config,
        clone.data.warnings,
        slice?.dataset_version_id ?? null,
        source?.status === 'dev' ? 'exploration' : 'official',
        clone.data.notes ?? [],
      ),
    })
  }, [clone.data, allSlices.data, protocols.data, cloneId, draft.clonedFrom])

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

  // Khám phá dùng protocol dev; máy local (ưu tiên online) chọn sẵn; mapping duy nhất chọn sẵn.
  useEffect(() => {
    if (draft.mode !== 'exploration' || draft.protocolId || !protocols.data) return
    const dev = protocols.data.find((p) => p.status === 'dev')
    if (dev) dispatch({ type: 'protocol', id: dev.id })
  }, [draft.mode, draft.protocolId, protocols.data])
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
  const estimate = useEstimate(draft.step === LAST_STEP && !searchInputError ? estimateBody : null)
  const target = targets.data?.find((t) => t.id === draft.targetId)
  const model = models.data?.find((m) => m.id === draft.modelId)
  const levelInputError = hasLevelInputError(draft.attacks, levelInputErrors)
  const stepOptions = {
    maxLimitSeconds: target?.max_time_limit_s,
    levelInputError,
    needsTrainingSlice: draft.required.some((lock) => lock.requiresTraining),
  }
  const advance = canAdvance(draft, stepOptions)
  const missing = missingHint(draft, stepOptions)

  const go = (step: Step) => dispatch({ type: 'go', step })

  const showErrors = (error: unknown) => {
    if (error instanceof ApiError && error.fields.length > 0) {
      const grouped = groupFieldErrors(error.fields)
      setErrors(grouped.byPath)
      if (grouped.firstStep) go(grouped.firstStep)
    }
  }

  const loadDraftResult = useCallback(
    (key: string, result: ExperimentClone, merge: boolean) =>
      dispatch({ type: 'drafted', key, clone: result, merge }),
    [],
  )

  const next = () => {
    if (!advance) return
    if (draft.step === 1) return go(2)
    if (draft.step !== 2) return
    // Bước 2 → 3: dựng bản nháp từ protocol và preset (giữ attack đã sửa nếu lựa chọn không đổi).
    const request = draftRequest(draft)
    if (!request) return
    const key = draftKeyOf(request)
    if (key === draft.draftKey && draft.attacks.length > 0) return go(3)
    setErrors({})
    drafting.mutate(request, {
      onSuccess: (result) => loadDraftResult(key, result, false),
      onError: showErrors,
    })
  }

  // Khám phá: thêm attack bằng chip = dựng lại bản nháp có thêm spec đó.
  const { mutate: redraft } = drafting
  const addAttack = useCallback(
    (attackSpecId: string, trainingSliceId?: string) => {
      const source = trainingSliceId ? { ...draft, trainingSliceId } : draft
      const request = draftRequest(source, [
        ...draft.attacks.map((a) => a.attackSpecId),
        attackSpecId,
      ])
      if (!request) return
      redraft(request, {
        onSuccess: (result) => loadDraftResult(draftKeyOf(request), result, true),
      })
    },
    [draft, redraft, loadDraftResult],
  )

  const submit = () => {
    if (!body) return
    setErrors({})
    create.mutate(body, {
      onSuccess: (experiment) => {
        clearDraft()
        void navigate(`/experiments/${experiment.id}`)
      },
      onError: showErrors,
    })
  }

  const stepProps = { draft, dispatch, errors }
  const cloneFailed = clone.isError || allSlices.isError
  const loadingClone = cloneId !== null && draft.clonedFrom !== cloneId && !cloneFailed
  const last = draft.step === LAST_STEP
  const nextTitle = STEPS.find(({ step }) => step === draft.step + 1)?.title ?? ''
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
        <p className="mt-2 max-w-[60ch] text-[15px] leading-6 text-white/85">{WIZARD_INTRO}</p>
      </div>
      <div className="panel relative z-10 mx-3 px-3 py-2 md:mx-6">
        <StepBar draft={draft} onGo={go} />
      </div>
      {cloneId !== null && cloneFailed && (
        <FormAlert>Không tải được cấu hình để nhân bản.</FormAlert>
      )}
      {drafting.isError && <FormAlert>{errorMessage(drafting.error)}</FormAlert>}
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
              Bước {draft.step} trên {LAST_STEP}
            </p>
            <h2 id="tieu-de-buoc" className="text-xl font-semibold">
              {STEPS[draft.step - 1].title}
            </h2>
            {STEP_HINTS[draft.step] && (
              <p className="max-w-[72ch] text-sm text-muted-foreground">{STEP_HINTS[draft.step]}</p>
            )}
          </div>
          {loadingClone ? (
            <p className="text-muted-foreground">Đang tải cấu hình để nhân bản…</p>
          ) : (
            <>
              {draft.step === 1 && <PurposeStep {...stepProps} />}
              {draft.step === 2 && (
                <DataStep {...stepProps} needsTrainingSlice={stepOptions.needsTrainingSlice} />
              )}
              {draft.step === 3 && (
                <>
                  <AttackStep
                    {...stepProps}
                    model={model}
                    estimate={estimate.data}
                    onInputError={(id, bad) =>
                      setLevelInputErrors((current) => ({ ...current, [id]: bad }))
                    }
                    onAdd={addAttack}
                    adding={drafting.isPending}
                  />
                  <ConfirmSection
                    draft={draft}
                    estimate={estimate.data}
                    estimating={estimate.isFetching}
                    errors={errors}
                    onName={(name) => dispatch({ type: 'name', name })}
                  />
                </>
              )}
            </>
          )}
          {estimate.isError && last && (
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
            {!advance && missing && (
              <p className="ml-auto text-right text-sm text-muted-foreground">{missing}</p>
            )}
            {!last ? (
              <Button
                onClick={next}
                disabled={!advance || drafting.isPending}
                className={cn(advance && 'ml-auto')}
              >
                {drafting.isPending ? 'Đang dựng danh sách attack…' : `Tiếp: ${nextTitle}`}
                <ChevronRight aria-hidden="true" />
              </Button>
            ) : (
              <Button
                size="lg"
                className={cn(advance && 'ml-auto')}
                onClick={submit}
                disabled={!advance || !body || create.isPending}
              >
                Tạo experiment
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
              Cập nhật theo từng lựa chọn. Chưa có gì được chạy cho tới khi bạn bấm "Tạo
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
          {!last ? (
            <Button onClick={next} disabled={!advance || drafting.isPending}>
              Tiếp
              <ChevronRight aria-hidden="true" />
            </Button>
          ) : (
            <Button onClick={submit} disabled={!advance || !body || create.isPending}>
              Tạo experiment
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}
