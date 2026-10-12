import { Gauge, Lock, Plus, TriangleAlert, X } from 'lucide-react'
import { useState } from 'react'
import type { Dispatch, ReactNode } from 'react'

import { AttackRisk, AttackTile } from '@/components/AttackTile'
import { type CardLook, MODE_ICON, PRESET_ICON } from '@/lib/card-looks'
import { SelectField } from '@/components/form/TextField'
import { LoadError } from '@/components/LoadError'
import { PageLoading } from '@/components/PageLoading'
import { Term } from '@/components/Term'
import type { AttackSpecView, EstimateResponse, ModelSummary } from '@/contracts/api'
import {
  ADD_ATTACK,
  ADVANCED,
  LIMIT_LABEL,
  MODE_CARD,
  NO_READY_MODEL,
  PROTOCOL_REQUIRED,
  REALISM_LABEL,
  SEARCH_ROW,
  SUGGESTED_LIMIT,
} from '@/copy/wizard'
import { ATTACK_EXPLAIN, ATTACK_KIND_LABEL, ATTACK_KINDS, ATTACK_PLAIN } from '@/lib/attack-kinds'
import { cn } from '@/lib/utils'

import {
  usableTrainingSlices,
  useAttackSpecs,
  useClassMappings,
  useComputeTargets,
  useDatasets,
  useModels,
  usePresets,
  useProtocol,
  useProtocols,
  useSlices,
  useTrainingSlices,
} from './api'
import { CustomLevel } from './CustomLevel'
import { levelCandidates, levelLabel, rangeText, specTitle } from './levels'
import { requiredLocks } from './protocol'
import { targetClassesOf } from './search'
import { ModeSwitch, SearchFields } from './SearchFields'
import {
  type Action,
  type AttackDraft,
  type Draft,
  lockOf,
  searchCostSummary,
  searchErrorKey,
  SEED,
} from './state'

export interface StepProps {
  draft: Draft
  dispatch: Dispatch<Action>
  /** Lỗi 422 theo đường dẫn trường. */
  errors: Record<string, string>
}

interface QueryLike {
  isPending: boolean
  isError: boolean
  isFetching: boolean
  refetch: () => unknown
}

/** Chờ tải / lỗi tải của một danh sách. */
function Loaded({ query, children }: { query: QueryLike; children: ReactNode }) {
  if (query.isPending) return <PageLoading />
  if (query.isError) {
    return <LoadError onRetry={() => void query.refetch()} retrying={query.isFetching} />
  }
  return <>{children}</>
}

function FieldErrorText({ message }: { message?: string }) {
  if (!message) return null
  return (
    <p role="alert" className="text-sm text-destructive">
      {message}
    </p>
  )
}

/** Thẻ chọn một trong nhiều (radio), vùng chạm ≥ 44px. */
export function ChoiceCard({
  selected,
  onSelect,
  children,
}: {
  selected: boolean
  onSelect: () => void
  children: ReactNode
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      onClick={onSelect}
      className={cn(
        'group flex min-h-11 w-full min-w-0 items-start gap-3 rounded-xl border bg-surface-solid p-4 text-left shadow-[0_1px_2px_rgba(16,24,40,0.05)] transition-[border-color,box-shadow,background-color] duration-150 focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none',
        selected
          ? 'border-navy shadow-[0_0_0_1px_var(--navy)]'
          : 'border-line hover:border-input hover:shadow-[0_4px_14px_rgba(16,24,40,0.07)]',
      )}
    >
      <span className="flex min-w-0 flex-1 flex-col items-start gap-1">{children}</span>
      <span
        aria-hidden
        className={cn(
          'mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full border-2 transition-colors',
          selected ? 'border-navy bg-navy' : 'border-input',
        )}
      >
        {selected && <span className="size-2 rounded-full bg-primary-foreground" />}
      </span>
    </button>
  )
}

function Badge({ tone = 'muted', children }: { tone?: 'muted' | 'warning'; children: ReactNode }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs',
        tone === 'warning' ? 'bg-threshold/12 text-threshold' : 'bg-muted text-muted-foreground',
      )}
    >
      {children}
    </span>
  )
}

// ---------------------------------------------------------------- bước 1: mục đích

/** Tiêu đề thẻ kèm ô icon nhỏ phía trước. */
export function CardTitle({ look, children }: { look?: CardLook; children: ReactNode }) {
  const Icon = look?.icon ?? Gauge
  return (
    <span className="flex items-center gap-2.5">
      <span className={cn('tile size-8', look?.tile)} aria-hidden="true">
        <Icon className="size-4" />
      </span>
      <span className="font-medium">{children}</span>
    </span>
  )
}

export function PurposeStep({ draft, dispatch, errors }: StepProps) {
  const protocols = useProtocols()
  const presets = usePresets()
  const active = protocols.data?.filter((p) => p.status === 'active') ?? []
  return (
    <div className="space-y-5">
      <p className="text-sm text-muted-foreground">
        <Term term="exploration" /> để thử nhanh và tự do; <Term term="official" /> chạy theo một{' '}
        <Term term="protocol" /> mà reviewer đã chốt tiêu chí trước khi có kết quả.
      </p>
      <div role="radiogroup" aria-label="Mode" className="grid gap-2 md:grid-cols-2">
        {(['exploration', 'official'] as const).map((mode) => (
          <ChoiceCard
            key={mode}
            selected={draft.mode === mode}
            onSelect={() => dispatch({ type: 'experimentMode', mode })}
          >
            <CardTitle look={MODE_ICON[mode]}>{MODE_CARD[mode].title}</CardTitle>
            <span className="text-sm text-muted-foreground">{MODE_CARD[mode].description}</span>
          </ChoiceCard>
        ))}
      </div>
      {draft.mode === 'official' && (
        <Loaded query={protocols}>
          {active.length === 0 ? (
            <p role="alert" className="text-sm text-destructive">
              Chưa có protocol nào đang dùng. Reviewer cần tạo protocol trước khi chạy kiểm thử
              chính thức.
            </p>
          ) : (
            <div className="max-w-md">
              <SelectField
                id="wizard-protocol"
                label="Protocol"
                value={draft.protocolId ?? ''}
                onChange={(event) => dispatch({ type: 'protocol', id: event.target.value })}
              >
                <option value="" disabled>
                  Chọn protocol
                </option>
                {active.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} v{p.version}
                  </option>
                ))}
              </SelectField>
            </div>
          )}
          {draft.protocolId && <ProtocolDetail protocolId={draft.protocolId} />}
        </Loaded>
      )}
      <FieldErrorText message={errors.protocol_id} />
      <section className="space-y-2">
        <h3 className="font-medium">Mức kiểm thử</h3>
        <Loaded query={presets}>
          <div role="radiogroup" aria-label="Preset" className="grid gap-2 md:grid-cols-3">
            {presets.data?.map((preset) => (
              <ChoiceCard
                key={preset.key}
                selected={draft.preset === preset.key}
                onSelect={() => dispatch({ type: 'preset', key: preset.key })}
              >
                <CardTitle look={PRESET_ICON[preset.key]}>{preset.title}</CardTitle>
                <span className="text-sm text-muted-foreground">{preset.description}</span>
              </ChoiceCard>
            ))}
          </div>
        </Loaded>
        <FieldErrorText message={errors.preset} />
      </section>
    </div>
  )
}

/** Phase 8: mục đích, attack bắt buộc và slice tối thiểu của protocol đang chọn. */
function ProtocolDetail({ protocolId }: { protocolId: string }) {
  const protocol = useProtocol(protocolId)
  const specs = useAttackSpecs()
  if (!protocol.data || !specs.data || protocol.data.status === 'dev') return null
  const body = protocol.data.body
  const { missing } = requiredLocks(body, specs.data)
  return (
    <div
      className="mt-3 space-y-2 rounded-xl bg-surface-raised p-4 text-sm"
      data-testid="protocol-chi-tiet"
    >
      <p>{body.description}</p>
      <p className="text-muted-foreground">
        Slice tối thiểu {body.min_slice_size} ảnh · {body.cases_to_review_per_attack} case review
        mỗi attack{body.forbid_dirty_runs ? ' · cấm code chưa commit' : ''}
      </p>
      <ul className="space-y-1">
        {body.required_attacks.map((a) => (
          <li key={a.attack_spec_name} className="flex items-center gap-2">
            <Lock aria-hidden="true" className="size-4 shrink-0" />
            {a.attack_spec_name}:{' '}
            {a.mode === 'grid'
              ? `quét lưới, level ${(a.grid?.levels ?? []).join(', ')}`
              : `tự tìm ngưỡng ${a.search?.threshold_kind} ${Math.round((a.search?.threshold ?? 0) * 100)}%`}
          </li>
        ))}
      </ul>
      {missing.length > 0 && (
        <p role="alert" className="text-destructive">
          Catalog không còn đúng version của: {missing.join(', ')}. Experiment theo protocol này sẽ
          không tuân thủ được; liên hệ reviewer để tạo version protocol mới.
        </p>
      )}
    </div>
  )
}

// ---------------------------------------------------------------- bước 2: model và dữ liệu

export function DataStep({
  draft,
  dispatch,
  errors,
  needsTrainingSlice,
}: StepProps & { needsTrainingSlice: boolean }) {
  const models = useModels()
  const datasets = useDatasets()
  const slices = useSlices(null, true)
  const mappings = useClassMappings(draft.datasetVersionId, draft.modelId)
  const targets = useComputeTargets()
  // `status` có mặc định `ready` trong contract (model trước R2 không có trường này).
  const ready =
    models.data?.filter((m) => m.status !== 'checking' && m.status !== 'check_failed') ?? []
  const datasetName = new Map(
    (datasets.data ?? []).flatMap((d) => d.versions.map((v) => [v.id, d.name] as const)),
  )
  // Phase 8: slice nhỏ hơn `min_slice_size` của protocol bị ẩn.
  const allSlices = slices.data ?? []
  const usable = allSlices.filter((s) => s.size >= (draft.minSliceSize ?? 0))
  const hidden = allSlices.length - usable.length
  const mappingList = mappings.data ?? []
  const target = targets.data?.find((t) => t.id === draft.targetId)
  return (
    <div className="grid max-w-2xl gap-4">
      <Loaded query={models}>
        {ready.length === 0 ? (
          <p role="alert" className="text-sm text-destructive">
            {NO_READY_MODEL}
          </p>
        ) : (
          <SelectField
            id="wizard-model"
            label="Model"
            value={draft.modelId ?? ''}
            error={errors.model_version_id}
            onChange={(event) => dispatch({ type: 'model', id: event.target.value })}
          >
            <option value="" disabled>
              Chọn model
            </option>
            {ready.map((model) => (
              <option key={model.id} value={model.id}>
                {model.name} · {model.framework} · {model.class_names.length} class
                {model.supports_gradients ? '' : ' · không hỗ trợ gradient'}
              </option>
            ))}
          </SelectField>
        )}
      </Loaded>
      <Loaded query={slices}>
        <SelectField
          id="wizard-slice"
          label="Dataset và slice"
          value={draft.sliceId ?? ''}
          error={errors.slice_id}
          onChange={(event) => {
            const slice = allSlices.find((s) => s.id === event.target.value)
            if (slice)
              dispatch({
                type: 'dataSlice',
                datasetVersionId: slice.dataset_version_id,
                sliceId: slice.id,
              })
          }}
        >
          <option value="" disabled>
            Chọn slice ảnh
          </option>
          {usable.map((slice) => (
            <option key={slice.id} value={slice.id}>
              {datasetName.get(slice.dataset_version_id) ?? 'Dataset'} · {slice.name} ({slice.size}{' '}
              ảnh)
            </option>
          ))}
        </SelectField>
        {hidden > 0 && (
          <p className="text-sm text-muted-foreground" data-testid="slice-an">
            Ẩn {hidden} slice nhỏ hơn {draft.minSliceSize} ảnh (protocol yêu cầu).
          </p>
        )}
      </Loaded>
      {draft.datasetVersionId && draft.modelId && (
        <Loaded query={mappings}>
          {mappingList.length === 0 ? (
            <p role="alert" className="text-sm text-destructive">
              Chưa có class mapping giữa dataset version này và model đã chọn. Admin cần đăng ký
              mapping (advertest-admin import-local) trước khi tạo experiment.
            </p>
          ) : mappingList.length === 1 ? (
            <p className="text-sm text-muted-foreground">
              Tự chọn class mapping duy nhất:{' '}
              {mappingList[0].preset ?? mappingList[0].mapping_sha256.slice(0, 12)}
            </p>
          ) : (
            <SelectField
              id="wizard-mapping"
              label="Class mapping"
              value={draft.mappingId ?? ''}
              error={errors.class_mapping_id}
              onChange={(event) => dispatch({ type: 'mapping', id: event.target.value })}
            >
              <option value="" disabled>
                Chọn class mapping
              </option>
              {mappingList.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.preset ?? m.mapping_sha256.slice(0, 12)} · {Object.keys(m.classes).length}{' '}
                  class gốc
                </option>
              ))}
            </SelectField>
          )}
        </Loaded>
      )}
      <Loaded query={targets}>
        <SelectField
          id="wizard-target"
          label="Máy chạy"
          value={draft.targetId ?? ''}
          error={errors.compute_target_id}
          onChange={(event) => {
            const picked = targets.data?.find((t) => t.id === event.target.value)
            if (picked)
              dispatch({
                type: 'target',
                id: picked.id,
                defaultLimitSeconds: picked.default_time_limit_s,
              })
          }}
        >
          <option value="" disabled>
            Chọn máy chạy
          </option>
          {targets.data?.map((t) => (
            <option key={t.id} value={t.id} disabled={t.kind !== 'local'}>
              {t.name} · {t.gpu_model ?? 'Chỉ CPU'} · {t.online ? 'đang online' : 'offline'} ·{' '}
              {t.queue_length} job đang chờ{t.kind === 'local' ? ' · miễn phí' : ''}
            </option>
          ))}
        </SelectField>
      </Loaded>
      {target && (
        <LimitSlider
          seconds={draft.limitSeconds}
          defaultSeconds={target.default_time_limit_s}
          maxSeconds={target.max_time_limit_s}
          error={errors['limit.value'] ?? errors['limit.kind']}
          onChange={(seconds) => dispatch({ type: 'limit', seconds })}
        />
      )}
      {needsTrainingSlice && (
        <DraftTrainingSlice draft={draft} dispatch={dispatch} error={errors.training_slice_id} />
      )}
    </div>
  )
}

/** Giới hạn thời gian bằng thanh trượt (Phase R3: không có ô gõ số), bước 5 phút. */
function LimitSlider({
  seconds,
  defaultSeconds,
  maxSeconds,
  error,
  onChange,
}: {
  seconds: number | null
  defaultSeconds: number
  maxSeconds: number
  error?: string
  onChange: (seconds: number) => void
}) {
  const max = Math.max(5, Math.floor(maxSeconds / 60))
  const suggested = Math.round(defaultSeconds / 60)
  const minutes = seconds === null ? suggested : Math.round(seconds / 60)
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-baseline justify-between gap-3">
        <label htmlFor="wizard-limit" className="text-[14px] font-semibold">
          {LIMIT_LABEL}
        </label>
        <span className="text-sm font-semibold tabular-nums">{minutes} phút</span>
      </div>
      <input
        id="wizard-limit"
        type="range"
        min={5}
        max={max}
        step={5}
        value={Math.min(minutes, max)}
        list="wizard-limit-suggested"
        aria-valuetext={`${minutes} phút`}
        aria-invalid={error ? true : undefined}
        onChange={(event) => onChange(Number(event.target.value) * 60)}
        className="min-h-11 w-full accent-[var(--navy)]"
      />
      <datalist id="wizard-limit-suggested">
        <option value={suggested} />
      </datalist>
      <p className="text-[13px] leading-5 text-muted-foreground">
        {SUGGESTED_LIMIT(suggested, max)}
      </p>
      <FieldErrorText message={error} />
    </div>
  )
}

/** Slice huấn luyện gửi kèm bản nháp (spec cần train): không giao slice đánh giá, cùng dataset
 * version, không quá `max_training_images` ảnh của spec. */
function DraftTrainingSlice({
  draft,
  dispatch,
  error,
  maxImages,
  onPick,
}: Pick<StepProps, 'draft' | 'dispatch'> & {
  error?: string
  maxImages?: number
  /** Gọi sau khi chọn (thêm attack cần train đang chờ slice huấn luyện). */
  onPick?: (id: string) => void
}) {
  const slices = useTrainingSlices(draft.sliceId)
  const specs = useAttackSpecs()
  const limit =
    maxImages ??
    Math.min(
      ...(specs.data ?? [])
        .filter((s) => s.requires_training)
        .map((s) => s.training?.max_training_images ?? Number.POSITIVE_INFINITY),
    )
  const usable = usableTrainingSlices(slices.data ?? [], draft.datasetVersionId, limit)
  if (draft.sliceId === null) return null
  return (
    <Loaded query={slices}>
      {usable.length === 0 ? (
        <p role="alert" className="text-sm text-destructive">
          Chưa có slice huấn luyện nào không giao với slice đánh giá và cùng dataset version. Tạo
          bằng advertest slice create --exclude-slice rồi đăng ký qua advertest-admin import-local.
        </p>
      ) : (
        <SelectField
          id="wizard-training-slice"
          label="Slice huấn luyện"
          hint="Attack cần train (patch) học trên slice này; mỗi level train một patch."
          value={draft.trainingSliceId ?? ''}
          error={error}
          onChange={(event) => {
            dispatch({ type: 'draftTrainingSlice', id: event.target.value })
            onPick?.(event.target.value)
          }}
        >
          <option value="" disabled>
            Chọn slice huấn luyện
          </option>
          {usable.map((slice) => (
            <option key={slice.id} value={slice.id}>
              {slice.name} ({slice.size} ảnh)
            </option>
          ))}
        </SelectField>
      )}
    </Loaded>
  )
}

// ---------------------------------------------------------------- bước 3: attack và xác nhận

export const EARLY_STOP_LABEL = 'Dừng sớm khi model đã sụp'
export const EARLY_STOP_HINT =
  'Bỏ các level lớn hơn của cùng attack khi mAP@0.5 sau biến đổi còn ≤ 5% mAP ảnh sạch. Chỉ áp cho attack quét lưới.'

function EarlyStopSwitch({ draft, dispatch }: Pick<StepProps, 'draft' | 'dispatch'>) {
  return (
    <div className="space-y-1">
      <label className="flex min-h-11 cursor-pointer items-center gap-3">
        <input
          type="checkbox"
          role="switch"
          className="size-5"
          checked={draft.earlyStop}
          onChange={(event) => dispatch({ type: 'earlyStop', on: event.target.checked })}
        />
        <span className="font-medium">{EARLY_STOP_LABEL}</span>
      </label>
      <p className="text-sm text-muted-foreground">{EARLY_STOP_HINT}</p>
      {draft.earlyStopMixed && (
        <p className="text-sm text-threshold">
          Cấu hình gốc có attack tắt dừng sớm: công tắc đang tắt cho mọi attack.
        </p>
      )}
    </div>
  )
}

/** Chip level có nhãn (Phase R3): bấm để bật/tắt; level bắt buộc theo protocol bị khóa. */
function LevelChips({
  spec,
  chosen,
  locked,
  onChange,
  error,
}: {
  spec: AttackSpecView
  chosen: AttackDraft
  locked: number[]
  onChange: (levels: number[]) => void
  error?: string
}) {
  const candidates = levelCandidates(spec, chosen.levels)
  const param = spec.primary_param
  return (
    <div className="space-y-1.5">
      <div
        role="group"
        aria-label={`Level của ${specTitle(spec)}`}
        className="flex flex-wrap gap-2"
      >
        {candidates.map((value) => {
          const on = chosen.levels.includes(value)
          const isLocked = locked.includes(value)
          const label = levelLabel(spec.metadata, value)
          return (
            <button
              key={value}
              type="button"
              data-level={value}
              aria-pressed={on}
              aria-disabled={isLocked ? true : undefined}
              title={isLocked ? PROTOCOL_REQUIRED : undefined}
              onClick={() => {
                if (isLocked) return
                onChange(
                  on
                    ? chosen.levels.filter((l) => l !== value)
                    : [...chosen.levels, value].sort((a, b) => a - b),
                )
              }}
              className={cn(
                'inline-flex min-h-11 items-center gap-1.5 rounded-full border px-3.5 text-sm tabular-nums transition-colors duration-150 focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none',
                on
                  ? 'border-navy bg-navy text-primary-foreground'
                  : 'border-line bg-surface-solid hover:border-input',
                isLocked && 'cursor-not-allowed',
              )}
            >
              {isLocked && <Lock aria-hidden="true" className="size-3" />}
              {label ? (
                <>
                  {label}
                  <span className={on ? 'opacity-75' : 'text-muted-foreground'}>{value}</span>
                </>
              ) : (
                value
              )}
            </button>
          )
        })}
      </div>
      <p className="text-xs text-muted-foreground">
        <Term term="level">Level</Term>: {param.name} ({rangeText(param)})
      </p>
      <FieldErrorText message={error} />
    </div>
  )
}

function AttackRow({
  spec,
  chosen,
  index,
  draft,
  dispatch,
  errors,
  model,
  sliceSize,
  targetClasses,
  estimate,
  onInputError,
}: StepProps & {
  spec: AttackSpecView
  chosen: AttackDraft
  index: number
  model: ModelSummary | undefined
  sliceSize: number | null
  targetClasses: string[] | null
  estimate: EstimateResponse | undefined
  onInputError: (key: string, bad: boolean) => void
}) {
  const lock = lockOf(draft, spec.id)
  const meta = spec.metadata
  const title = specTitle(spec)
  const description = meta?.description ?? ATTACK_EXPLAIN[spec.name]?.how ?? ATTACK_PLAIN[spec.name]
  const param = spec.primary_param
  const canType =
    chosen.mode === 'grid' &&
    !spec.requires_training &&
    !(param.type === 'discrete' && param.values)
  const incompatible = spec.requires_gradients && model?.supports_gradients === false
  const serverError =
    [
      errors[`attacks.${index}.grid.levels`],
      errors[`attacks.${index}.attack_spec_id`],
      errors[`attacks.${index}.spec_sha256`],
      errors[`attacks.${index}.mode`],
      errors[`attacks.${index}.training_slice_id`],
    ]
      .filter(Boolean)
      .join('; ') || undefined
  return (
    <li
      data-testid="attack-row"
      data-attack={spec.name}
      className="space-y-3 rounded-xl border border-line bg-surface-solid p-4 shadow-[0_1px_2px_rgba(16,24,40,0.05)]"
    >
      <div className="flex items-start gap-3">
        <AttackTile spec={spec} />
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <p className="font-medium">
            {title}{' '}
            <span className="text-sm font-normal text-muted-foreground">
              {title !== spec.name && `${spec.name} `}v{spec.version}
            </span>
          </p>
          {description && <p className="text-sm leading-5 text-muted-foreground">{description}</p>}
          <AttackRisk name={spec.name} />
          <div className="flex flex-wrap gap-1.5">
            <Badge>{ATTACK_KIND_LABEL[spec.kind]}</Badge>
            {meta && <Badge>{REALISM_LABEL[meta.realism]}</Badge>}
            {lock && (
              <Badge>
                <Lock aria-hidden="true" className="size-3" />
                {PROTOCOL_REQUIRED}
              </Badge>
            )}
          </div>
        </div>
        {!lock && (
          <button
            type="button"
            aria-label={`Bỏ attack ${title}`}
            onClick={() =>
              dispatch({
                type: 'toggleAttack',
                attackSpecId: spec.id,
                specSha256: spec.spec_sha256,
                requiresTraining: spec.requires_training === true,
              })
            }
            className="-mt-1 -mr-1 flex size-11 shrink-0 items-center justify-center rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
          >
            <X aria-hidden="true" className="size-4" />
          </button>
        )}
      </div>
      {incompatible && (
        <p className="flex items-center gap-2 text-sm text-threshold">
          <TriangleAlert aria-hidden="true" className="size-4 shrink-0" />
          Attack cần gradient, model không hỗ trợ: các run sẽ bị bỏ qua.
        </p>
      )}
      {chosen.mode === 'grid' ? (
        <LevelChips
          spec={spec}
          chosen={chosen}
          locked={lock?.levels ?? []}
          error={serverError}
          onChange={(levels) => dispatch({ type: 'levels', attackSpecId: spec.id, levels })}
        />
      ) : (
        <div className="space-y-1 text-sm">
          <p>{SEARCH_ROW}</p>
          {estimate && searchCostSummary(estimate, spec.id) && (
            <p className="text-muted-foreground">{searchCostSummary(estimate, spec.id)}</p>
          )}
          <FieldErrorText message={serverError} />
        </div>
      )}
      <details className="group rounded-lg border border-line px-3 py-1 text-sm">
        <summary className="flex min-h-11 cursor-pointer items-center font-medium">
          {ADVANCED}
        </summary>
        <div className="space-y-3 pb-3">
          {canType && (
            <CustomLevel
              param={param}
              levels={chosen.levels}
              onChange={(levels) => dispatch({ type: 'levels', attackSpecId: spec.id, levels })}
            />
          )}
          <ModeSwitch
            spec={spec}
            chosen={chosen}
            sliceSize={sliceSize}
            dispatch={dispatch}
            protocolLocked={lock !== undefined}
          />
          {chosen.mode === 'search' && chosen.search && (
            <SearchFields
              spec={spec}
              index={index}
              search={chosen.search}
              sliceSize={sliceSize}
              targetClasses={targetClasses}
              serverErrors={errors}
              dispatch={dispatch}
              onInputError={(bad) => onInputError(searchErrorKey(spec.id), bad)}
              estimate={estimate}
              thresholdLocked={lock?.mode === 'search'}
            />
          )}
          <p className="text-xs text-muted-foreground">Seed cố định: {SEED}</p>
        </div>
      </details>
    </li>
  )
}

export function AttackStep({
  draft,
  dispatch,
  errors,
  model,
  estimate,
  onInputError,
  onAdd,
  adding,
}: StepProps & {
  model: ModelSummary | undefined
  estimate: EstimateResponse | undefined
  onInputError: (key: string, bad: boolean) => void
  /** Khám phá: thêm attack (dựng lại bản nháp có attack này). */
  onAdd: (attackSpecId: string, trainingSliceId?: string) => void
  adding: boolean
}) {
  const specs = useAttackSpecs()
  const slices = useSlices(draft.datasetVersionId)
  const mappings = useClassMappings(draft.datasetVersionId, draft.modelId)
  const [pending, setPending] = useState<string | null>(null)
  const all = specs.data ?? []
  const byId = new Map(all.map((s) => [s.id, s]))
  // Kiểm tra tập con và class ngay trên form; chưa tải xong thì để backend kiểm tra.
  const sliceSize = slices.data?.find((s) => s.id === draft.sliceId)?.size ?? null
  const mapping = mappings.data?.find((m) => m.id === draft.mappingId)
  const targetClasses = mapping ? targetClassesOf(mapping.classes) : null
  const chosenIds = new Set(draft.attacks.map((a) => a.attackSpecId))
  const addable = all.filter((s) => !chosenIds.has(s.id))
  return (
    <div className="space-y-4">
      <FieldErrorText message={errors.attacks} />
      <Loaded query={specs}>
        <ul className="space-y-3">
          {draft.attacks.map((chosen, index) => {
            const spec = byId.get(chosen.attackSpecId)
            if (!spec) return null
            return (
              <AttackRow
                key={chosen.attackSpecId}
                spec={spec}
                chosen={chosen}
                index={index}
                draft={draft}
                dispatch={dispatch}
                errors={errors}
                model={model}
                sliceSize={sliceSize}
                targetClasses={targetClasses}
                estimate={estimate}
                onInputError={onInputError}
              />
            )
          })}
        </ul>
        {draft.mode === 'exploration' && addable.length > 0 && (
          <section className="space-y-2">
            <h3 className="font-medium">{ADD_ATTACK}</h3>
            <p className="text-sm text-muted-foreground">
              Bấm thẻ để thêm. Mỗi thẻ nói attack làm gì với ảnh và mô phỏng rủi ro nào ngoài đời.
            </p>
            {ATTACK_KINDS.map((kind) => {
              const group = addable.filter((spec) => spec.kind === kind)
              if (group.length === 0) return null
              return (
                <div key={kind} className="space-y-2">
                  <p className="text-sm font-medium text-muted-foreground">
                    {ATTACK_KIND_LABEL[kind]}
                  </p>
                  <div className="grid gap-2 md:grid-cols-2">
                    {group.map((spec) => (
                      <button
                        key={spec.id}
                        type="button"
                        disabled={adding}
                        aria-label={`Thêm ${specTitle(spec)}`}
                        onClick={() => {
                          if (spec.requires_training && !draft.trainingSliceId) setPending(spec.id)
                          else onAdd(spec.id)
                        }}
                        className="flex min-h-11 items-start gap-3 rounded-xl border border-dashed border-input bg-surface-solid p-3 text-left transition-colors hover:border-navy disabled:opacity-60 focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
                      >
                        <AttackTile spec={spec} />
                        <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                          <span className="font-semibold">
                            {specTitle(spec)}{' '}
                            <span className="text-xs font-normal text-muted-foreground">
                              v{spec.version}
                            </span>
                          </span>
                          <span className="text-[13px] leading-5 text-muted-foreground">
                            {spec.metadata?.description ??
                              ATTACK_EXPLAIN[spec.name]?.how ??
                              ATTACK_PLAIN[spec.name]}
                          </span>
                          <AttackRisk name={spec.name} />
                        </span>
                        <Plus aria-hidden="true" className="mt-1 size-4 shrink-0" />
                      </button>
                    ))}
                  </div>
                </div>
              )
            })}
            {pending && (
              <div className="max-w-md">
                <DraftTrainingSlice
                  draft={draft}
                  dispatch={dispatch}
                  maxImages={byId.get(pending)?.training?.max_training_images}
                  onPick={(id) => {
                    onAdd(pending, id)
                    setPending(null)
                  }}
                />
              </div>
            )}
          </section>
        )}
      </Loaded>
      <details className="rounded-lg border border-line px-3 py-1 text-sm">
        <summary className="flex min-h-11 cursor-pointer items-center font-medium">
          {ADVANCED}: mọi attack
        </summary>
        <div className="pb-3">
          <EarlyStopSwitch draft={draft} dispatch={dispatch} />
        </div>
      </details>
    </div>
  )
}
