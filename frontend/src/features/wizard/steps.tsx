import { TriangleAlert } from 'lucide-react'
import type { Dispatch, ReactNode } from 'react'

import { LoadError } from '@/components/LoadError'
import { PageLoading } from '@/components/PageLoading'
import type {
  AttackSpec,
  ComputeTargetPublic,
  EstimateResponse,
  ModelSummary,
} from '@/contracts/api'
import { ATTACK_KIND_LABEL, ATTACK_KINDS } from '@/lib/attack-kinds'
import { cn } from '@/lib/utils'

import { Button } from '@/components/ui/button'

import {
  usableTrainingSlices,
  useAttackSpecs,
  useClassMappings,
  useComputeTargets,
  useDatasets,
  useModels,
  useProtocols,
  useSlices,
  useTrainingSlices,
} from './api'
import { LevelChips } from './LevelChips'
import { catalogPreset, suggestedLevels } from './levels'
import { targetClassesOf } from './search'
import { ModeSwitch, SearchFields } from './SearchFields'
import {
  type Action,
  type AttackDraft,
  type Draft,
  formatDuration,
  searchErrorKey,
  SEED,
  trainingSummary,
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
function ChoiceCard({
  selected,
  onSelect,
  children,
  disabled = false,
}: {
  selected: boolean
  onSelect: () => void
  children: ReactNode
  disabled?: boolean
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      disabled={disabled}
      onClick={onSelect}
      className={cn(
        'flex min-h-11 w-full min-w-0 flex-col items-start gap-1 rounded-lg border p-3 text-left transition-colors',
        selected ? 'border-primary bg-primary/5 ring-2 ring-primary/30' : 'hover:bg-muted',
        disabled && 'cursor-not-allowed opacity-60',
      )}
    >
      {children}
    </button>
  )
}

function Badge({ tone = 'muted', children }: { tone?: 'muted' | 'warning'; children: ReactNode }) {
  return (
    <span
      className={cn(
        'rounded-full px-2 py-0.5 text-xs',
        tone === 'warning'
          ? 'bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200'
          : 'bg-muted text-muted-foreground',
      )}
    >
      {children}
    </span>
  )
}

// ---------------------------------------------------------------- bước 1: protocol

export function ProtocolStep({ draft, dispatch, errors }: StepProps) {
  const protocols = useProtocols()
  return (
    <Loaded query={protocols}>
      <div role="radiogroup" aria-label="Protocol" className="grid gap-2">
        {protocols.data?.map((p) => (
          <ChoiceCard
            key={p.id}
            selected={draft.protocolId === p.id}
            onSelect={() => dispatch({ type: 'protocol', id: p.id })}
          >
            <span className="font-medium">
              {p.name} <span className="text-sm text-muted-foreground">v{p.version}</span>
            </span>
            {p.status === 'dev' && <Badge tone="warning">Dev – không gửi duyệt được</Badge>}
          </ChoiceCard>
        ))}
      </div>
      <FieldErrorText message={errors.protocol_id} />
    </Loaded>
  )
}

// ---------------------------------------------------------------- bước 2: model

export function ModelStep({ draft, dispatch, errors }: StepProps) {
  const models = useModels()
  return (
    <Loaded query={models}>
      <div role="radiogroup" aria-label="Model" className="grid gap-2 md:grid-cols-2">
        {models.data?.map((model) => (
          <ChoiceCard
            key={model.id}
            selected={draft.modelId === model.id}
            onSelect={() => dispatch({ type: 'model', id: model.id })}
          >
            <span className="font-medium break-all">{model.name}</span>
            <span className="text-sm text-muted-foreground">
              {model.framework} · {model.class_names.length} class · ảnh {model.input_size}px
            </span>
            {!model.supports_gradients && <Badge tone="warning">Không hỗ trợ gradient</Badge>}
          </ChoiceCard>
        ))}
      </div>
      <FieldErrorText message={errors.model_version_id} />
    </Loaded>
  )
}

// ---------------------------------------------------------------- bước 3: dataset và slice

export function DatasetStep({ draft, dispatch, errors }: StepProps) {
  const datasets = useDatasets()
  const slices = useSlices(draft.datasetVersionId)
  const mappings = useClassMappings(draft.datasetVersionId, draft.modelId)
  const mappingList = mappings.data ?? []
  return (
    <div className="space-y-4">
      <section className="space-y-2">
        <h3 className="font-medium">Dataset version</h3>
        <Loaded query={datasets}>
          <div role="radiogroup" aria-label="Dataset version" className="grid gap-2">
            {datasets.data?.flatMap((dataset) =>
              dataset.versions.map((version) => (
                <ChoiceCard
                  key={version.id}
                  selected={draft.datasetVersionId === version.id}
                  onSelect={() => dispatch({ type: 'datasetVersion', id: version.id })}
                >
                  <span className="font-medium">{dataset.name}</span>
                  <span className="text-sm text-muted-foreground">
                    {version.num_images} ảnh · {version.manifest_sha256.slice(0, 12)}
                  </span>
                  {!dataset.anonymized && (
                    <Badge>Chưa ẩn danh: ảnh failure case được làm mờ mặt và biển số</Badge>
                  )}
                </ChoiceCard>
              )),
            )}
          </div>
        </Loaded>
      </section>
      {draft.datasetVersionId && (
        <section className="space-y-2">
          <h3 className="font-medium">Slice</h3>
          <Loaded query={slices}>
            {slices.data?.length === 0 ? (
              <p className="text-sm text-muted-foreground">Dataset version này chưa có slice.</p>
            ) : (
              <div role="radiogroup" aria-label="Slice" className="grid gap-2 md:grid-cols-2">
                {slices.data?.map((slice) => (
                  <ChoiceCard
                    key={slice.id}
                    selected={draft.sliceId === slice.id}
                    onSelect={() => dispatch({ type: 'slice', id: slice.id })}
                  >
                    <span className="font-medium break-all">{slice.name}</span>
                    <span className="text-sm text-muted-foreground">
                      {slice.size} ảnh · seed {slice.seed}
                    </span>
                  </ChoiceCard>
                ))}
              </div>
            )}
          </Loaded>
          <FieldErrorText message={errors.slice_id} />
        </section>
      )}
      {draft.datasetVersionId && draft.modelId && (
        <section className="space-y-2">
          <h3 className="font-medium">Class mapping</h3>
          <Loaded query={mappings}>
            {mappingList.length === 0 ? (
              <p role="alert" className="text-sm text-destructive">
                Chưa có class mapping giữa dataset version này và model đã chọn. Admin cần đăng ký
                mapping (advertest-admin import-local) trước khi tạo experiment.
              </p>
            ) : mappingList.length === 1 ? (
              <p className="text-sm text-muted-foreground">
                Tự chọn mapping duy nhất:{' '}
                {mappingList[0].preset ?? mappingList[0].mapping_sha256.slice(0, 12)}
              </p>
            ) : (
              <div role="radiogroup" aria-label="Class mapping" className="grid gap-2">
                {mappingList.map((m) => (
                  <ChoiceCard
                    key={m.id}
                    selected={draft.mappingId === m.id}
                    onSelect={() => dispatch({ type: 'mapping', id: m.id })}
                  >
                    <span className="font-medium">{m.preset ?? m.mapping_sha256.slice(0, 12)}</span>
                    <span className="text-sm text-muted-foreground">
                      {Object.keys(m.classes).length} class gốc
                    </span>
                  </ChoiceCard>
                ))}
              </div>
            )}
          </Loaded>
          <FieldErrorText message={errors.class_mapping_id} />
        </section>
      )}
    </div>
  )
}

// ---------------------------------------------------------------- bước 4: attack

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
        <p className="text-sm text-amber-800 dark:text-amber-300">
          Cấu hình gốc có attack tắt dừng sớm: công tắc đang tắt cho mọi attack.
        </p>
      )}
    </div>
  )
}

/** Chọn slice huấn luyện cho attack cần train (patch): không giao slice đánh giá, cùng dataset
 * version, không quá `max_training_images` ảnh. */
function TrainingSliceField({
  draft,
  dispatch,
  spec,
  chosen,
  error,
  estimate,
}: Pick<StepProps, 'draft' | 'dispatch'> & {
  spec: AttackSpec
  chosen: AttackDraft
  error?: string
  estimate: EstimateResponse | undefined
}) {
  const slices = useTrainingSlices(draft.sliceId)
  const maxImages = spec.training?.max_training_images ?? 0
  const usable = usableTrainingSlices(slices.data ?? [], draft.datasetVersionId, maxImages)
  return (
    <section className="space-y-2">
      <h4 className="text-sm font-medium">Slice huấn luyện (bắt buộc)</h4>
      <Loaded query={slices}>
        {usable.length === 0 ? (
          <p role="alert" className="text-sm text-destructive">
            Chưa có slice huấn luyện nào không giao với slice đánh giá, cùng dataset version và tối
            đa {maxImages} ảnh. Tạo bằng advertest slice create --exclude-slice rồi đăng ký qua
            advertest-admin import-local.
          </p>
        ) : (
          <div
            role="radiogroup"
            aria-label={`Slice huấn luyện của ${spec.name}`}
            className="grid gap-2 md:grid-cols-2"
          >
            {usable.map((slice) => (
              <ChoiceCard
                key={slice.id}
                selected={chosen.trainingSliceId === slice.id}
                onSelect={() =>
                  dispatch({ type: 'trainingSlice', attackSpecId: spec.id, id: slice.id })
                }
              >
                <span className="font-medium break-all">{slice.name}</span>
                <span className="text-sm text-muted-foreground">
                  {slice.size} ảnh · seed {slice.seed}
                </span>
              </ChoiceCard>
            ))}
          </div>
        )}
      </Loaded>
      <p className="text-sm text-muted-foreground">
        Mỗi level (tỉ lệ diện tích) train một patch trên slice này; patch đã có thì dùng lại.
      </p>
      {estimate && chosen.trainingSliceId && (
        <p className="text-sm" data-testid="thoi-gian-train">
          {trainingSummary(estimate, spec.id)}
        </p>
      )}
      <FieldErrorText message={error} />
    </section>
  )
}

export function AttackStep({
  draft,
  dispatch,
  errors,
  model,
  onLevelInputError,
  estimate,
}: StepProps & {
  model: ModelSummary | undefined
  onLevelInputError: (id: string, bad: boolean) => void
  /** Ước lượng hiện tại (để hiện thời gian train patch, Phase 6). */
  estimate?: EstimateResponse
}) {
  const specs = useAttackSpecs()
  const slices = useSlices(draft.datasetVersionId)
  const mappings = useClassMappings(draft.datasetVersionId, draft.modelId)
  const all = specs.data ?? []
  // Kiểm tra tập con và class ngay trên form; chưa tải xong thì để backend kiểm tra.
  const sliceSize = slices.data?.find((s) => s.id === draft.sliceId)?.size ?? null
  const mapping = mappings.data?.find((m) => m.id === draft.mappingId)
  const targetClasses = mapping ? targetClassesOf(mapping.classes) : null
  return (
    <div className="space-y-4">
      <EarlyStopSwitch draft={draft} dispatch={dispatch} />
      <FieldErrorText message={errors.attacks} />
      <Loaded query={specs}>
        <div className="space-y-1">
          <Button
            type="button"
            variant="outline"
            onClick={() => dispatch({ type: 'preset', attacks: catalogPreset(all) })}
          >
            Toàn bộ catalog
          </Button>
          <p className="text-sm text-muted-foreground">
            Chọn mọi attack với bộ level gợi ý (
            {catalogPreset(all).reduce((n, a) => n + a.levels.length, 0)} run).
          </p>
        </div>
        {ATTACK_KINDS.map((kind) => {
          const title = ATTACK_KIND_LABEL[kind]
          const list = all.filter((spec) => spec.kind === kind)
          if (list.length === 0) return null
          return (
            <section key={kind} className="space-y-2">
              <h3 className="font-medium">{title}</h3>
              {list.map((spec) => {
                const index = draft.attacks.findIndex((a) => a.attackSpecId === spec.id)
                const chosen = index >= 0 ? draft.attacks[index] : undefined
                const incompatible = spec.requires_gradients && model?.supports_gradients === false
                return (
                  <div key={spec.id} className="space-y-3 rounded-lg border p-3">
                    <label className="flex min-h-11 cursor-pointer items-center gap-3">
                      <input
                        type="checkbox"
                        className="size-5"
                        checked={chosen !== undefined}
                        onChange={() =>
                          dispatch({
                            type: 'toggleAttack',
                            attackSpecId: spec.id,
                            specSha256: spec.spec_sha256,
                            requiresTraining: spec.requires_training === true,
                          })
                        }
                      />
                      <span className="font-medium">
                        {spec.name}{' '}
                        <span className="text-sm text-muted-foreground">v{spec.version}</span>
                      </span>
                    </label>
                    {incompatible && (
                      <p className="flex items-center gap-2 text-sm text-amber-800 dark:text-amber-300">
                        <TriangleAlert aria-hidden="true" className="size-4 shrink-0" />
                        Attack cần gradient, model không hỗ trợ: các run sẽ bị bỏ qua.
                      </p>
                    )}
                    {chosen && (
                      <ModeSwitch
                        spec={spec}
                        chosen={chosen}
                        sliceSize={sliceSize}
                        dispatch={dispatch}
                      />
                    )}
                    {chosen?.mode === 'search' && chosen.search && (
                      <SearchFields
                        spec={spec}
                        index={index}
                        search={chosen.search}
                        sliceSize={sliceSize}
                        targetClasses={targetClasses}
                        serverErrors={errors}
                        dispatch={dispatch}
                        onInputError={(bad) => onLevelInputError(searchErrorKey(spec.id), bad)}
                        estimate={estimate}
                      />
                    )}
                    {chosen?.mode === 'grid' && (
                      <>
                        <LevelChips
                          param={spec.primary_param}
                          levels={chosen.levels}
                          suggested={suggestedLevels(spec)}
                          onChange={(levels) =>
                            dispatch({ type: 'levels', attackSpecId: spec.id, levels })
                          }
                          serverError={
                            [
                              errors[`attacks.${index}.grid.levels`],
                              errors[`attacks.${index}.attack_spec_id`],
                              errors[`attacks.${index}.spec_sha256`],
                              errors[`attacks.${index}.mode`],
                            ]
                              .filter(Boolean)
                              .join('; ') || undefined
                          }
                          onInputError={(bad) => onLevelInputError(spec.id, bad)}
                        />
                        {chosen.requiresTraining && (
                          <TrainingSliceField
                            draft={draft}
                            dispatch={dispatch}
                            spec={spec}
                            chosen={chosen}
                            error={errors[`attacks.${index}.training_slice_id`]}
                            estimate={estimate}
                          />
                        )}
                        <p className="text-xs text-muted-foreground">Seed cố định: {SEED}</p>
                      </>
                    )}
                  </div>
                )
              })}
            </section>
          )
        })}
      </Loaded>
    </div>
  )
}

// ---------------------------------------------------------------- bước 5: máy chạy và giới hạn

export function TargetStep({
  draft,
  dispatch,
  errors,
  estimate,
}: StepProps & { estimate: EstimateResponse | undefined }) {
  const targets = useComputeTargets()
  const selected = targets.data?.find((t) => t.id === draft.targetId)
  const minutes = draft.limitSeconds === null ? '' : String(Math.round(draft.limitSeconds / 60))
  const maxMinutes = selected ? Math.floor(selected.max_time_limit_s / 60) : undefined
  const tooLong = selected !== undefined && (draft.limitSeconds ?? 0) > selected.max_time_limit_s
  return (
    <div className="space-y-4">
      <Loaded query={targets}>
        <div role="radiogroup" aria-label="Máy chạy" className="grid gap-2 md:grid-cols-2">
          {targets.data?.map((target: ComputeTargetPublic) => (
            <ChoiceCard
              key={target.id}
              selected={draft.targetId === target.id}
              disabled={target.kind !== 'local'}
              onSelect={() =>
                dispatch({
                  type: 'target',
                  id: target.id,
                  defaultLimitSeconds: target.default_time_limit_s,
                })
              }
            >
              <span className="font-medium">{target.name}</span>
              <span className="text-sm text-muted-foreground">
                {target.gpu_model ?? 'Chỉ CPU'} · {target.online ? 'Đang online' : 'Offline'} ·{' '}
                {target.queue_length} job đang chờ
              </span>
              {target.kind === 'local' && <Badge>Miễn phí – máy local</Badge>}
              {draft.targetId === target.id && (
                <span className="text-sm">
                  Ước lượng: {formatDuration(estimate?.total_seconds)}
                </span>
              )}
            </ChoiceCard>
          ))}
        </div>
      </Loaded>
      <FieldErrorText message={errors.compute_target_id} />
      {selected && (
        <div className="flex max-w-xs flex-col gap-1.5">
          <label htmlFor="gioi-han-phut" className="text-sm font-medium">
            Giới hạn thời gian (phút)
          </label>
          <input
            id="gioi-han-phut"
            type="number"
            inputMode="numeric"
            min={1}
            max={maxMinutes}
            value={minutes}
            aria-invalid={tooLong || errors['limit.value'] ? true : undefined}
            onChange={(event) => {
              const value = Number(event.target.value)
              dispatch({
                type: 'limit',
                seconds: event.target.value === '' || !Number.isFinite(value) ? null : value * 60,
              })
            }}
            className="min-h-11 w-full rounded-lg border border-input bg-background px-3 text-base aria-invalid:border-destructive"
          />
          <p className="text-sm text-muted-foreground">
            Mặc định {Math.round(selected.default_time_limit_s / 60)} phút, tối đa {maxMinutes}{' '}
            phút. Chạm giới hạn thì dừng và giữ kết quả một phần.
          </p>
          {tooLong && (
            <p role="alert" className="text-sm text-destructive">
              Vượt giới hạn tối đa {maxMinutes} phút của {selected.name}.
            </p>
          )}
          <FieldErrorText message={errors['limit.value'] ?? errors['limit.kind']} />
        </div>
      )}
    </div>
  )
}
