import { useQueryClient } from '@tanstack/react-query'
import { Clock, ImageUp, SearchX, TriangleAlert } from 'lucide-react'
import { type DragEvent, type FormEvent, useState } from 'react'
import { Link, useSearchParams } from 'react-router'

import { ApiError } from '@/api/errors'
import { errorMessage } from '@/api/messages'
import { useMe } from '@/auth/useMe'
import { BoxCanvas } from '@/components/case-viewer/BoxCanvas'
import type { BoxSet } from '@/components/case-viewer/boxes'
import { BoxSwatch } from '@/components/case-viewer/BoxSwatch'
import { EmptyState } from '@/components/EmptyState'
import { FormAlert } from '@/components/FormAlert'
import { SelectField, TextField } from '@/components/form/TextField'
import { LoadError } from '@/components/LoadError'
import { PageLoading } from '@/components/PageLoading'
import { StatusBadge } from '@/components/status/StatusBadge'
import { Term } from '@/components/Term'
import { Button } from '@/components/ui/button'
import type { QuickTryLevel, QuickTryView } from '@/contracts/api'
import { quickTryObjectStatusValues } from '@/contracts/schemas'
import { QUICK_TRY_COPY as COPY } from '@/copy/quick-try'
import { artifactSrc } from '@/features/experiments/api'
import { useAttackSpecs, useModels, usePresets } from '@/features/wizard/api'
import { specTitle } from '@/features/wizard/levels'
import { ChoiceCard } from '@/features/wizard/steps'
import { PageHero } from '@/layout/PageHero'
import { cn } from '@/lib/utils'

import {
  isPending,
  lastQuickTry,
  type Preset,
  rememberQuickTry,
  useCreateQuickTry,
  useQuickTry,
} from './api'
import {
  ALL_LAYERS,
  attackedBoxes,
  cleanBoxes,
  expiryTime,
  imageError,
  levelText,
  QUICK_TRY_LAYERS,
  type QuickTryLayer,
  quickTryAttacks,
  readyModels,
  statusCounts,
} from './logic'

const ID_PARAM = 'id'

/** `/quick-try` (requirements.md Phase R3, mục Thử nhanh; permission `quick_try.use`). */
export function QuickTryPage() {
  const [params, setParams] = useSearchParams()
  const id = params.get(ID_PARAM)
  const show = (next: string | null) => setParams(next ? { [ID_PARAM]: next } : {})
  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-5 p-4 md:p-8">
      <PageHero compact title={COPY.title} description={COPY.description} />
      <QuickTryForm onCreated={show} />
      {id && <QuickTryStatus key={id} id={id} onReset={() => show(null)} />}
    </div>
  )
}

function QuickTryForm({ onCreated }: { onCreated: (id: string) => void }) {
  const me = useMe()
  const models = useModels()
  const specs = useAttackSpecs()
  const presets = usePresets()
  const create = useCreateQuickTry()
  const queryClient = useQueryClient()
  const [modelId, setModelId] = useState('')
  const [attackId, setAttackId] = useState('')
  const [preset, setPreset] = useState<Preset>('standard')
  const [file, setFile] = useState<File | null>(null)
  const [dragging, setDragging] = useState(false)
  const [submitted, setSubmitted] = useState(false)

  if (models.isPending || specs.isPending) return <PageLoading />
  if (models.isError || specs.isError)
    return (
      <LoadError
        onRetry={() => {
          void models.refetch()
          void specs.refetch()
        }}
      />
    )

  const ready = readyModels(models.data)
  const model = ready.find((m) => m.id === modelId) ?? ready[0]
  const attacks = quickTryAttacks(specs.data, model)
  const attack = attacks.find((s) => s.id === attackId) ?? attacks[0]
  // Mặc định Tiêu chuẩn; danh sách preset không có thì lấy preset đầu tiên.
  const presetKey = presets.data?.some((p) => p.key === preset)
    ? preset
    : (presets.data?.[0]?.key ?? preset)
  const fileError = file ? imageError(file) : submitted ? COPY.imageMissing : null

  function chooseFile(next: File | null | undefined) {
    setFile(next ?? null)
    create.reset()
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    setDragging(false)
    chooseFile(event.dataTransfer.files[0])
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    setSubmitted(true)
    if (!model || !attack || !file || imageError(file)) return
    create.mutate(
      { modelVersionId: model.id, attackSpecId: attack.id, preset: presetKey, image: file },
      {
        onSuccess: (view) => {
          if (me.data) rememberQuickTry(me.data.id, view.id)
          queryClient.setQueryData(['quick-tries', view.id], view)
          onCreated(view.id)
        },
      },
    )
  }

  return (
    <form
      className="panel flex flex-col gap-4 p-5 md:p-6"
      aria-label={COPY.formTitle}
      onSubmit={submit}
      noValidate
    >
      <h2 className="text-base font-semibold">{COPY.formTitle}</h2>
      <div className="grid gap-4 md:grid-cols-2">
        <SelectField
          label="Model"
          value={model?.id ?? ''}
          onChange={(e) => setModelId(e.target.value)}
          disabled={ready.length === 0}
        >
          {ready.map((m) => (
            <option key={m.id} value={m.id}>
              {m.name}
              {m.supports_gradients ? '' : ' · không hỗ trợ gradient'}
            </option>
          ))}
        </SelectField>
        <SelectField
          label="Attack"
          hint={
            <>
              {COPY.attackHint.noPatch} <Term term="patch" />.{' '}
              <Term term="white_box">{COPY.attackHint.gradient}</Term>{' '}
              {COPY.attackHint.gradientRest}
            </>
          }
          value={attack?.id ?? ''}
          onChange={(e) => setAttackId(e.target.value)}
          disabled={attacks.length === 0}
        >
          {attacks.map((s) => (
            <option key={s.id} value={s.id}>
              {specTitle(s)} ({s.name})
            </option>
          ))}
        </SelectField>
      </div>
      {presets.data && (
        <div role="radiogroup" aria-label="Preset" className="grid gap-2 md:grid-cols-3">
          {presets.data.map((p) => (
            <ChoiceCard
              key={p.key}
              selected={presetKey === p.key}
              onSelect={() => setPreset(p.key)}
            >
              <span className="font-medium">{p.title}</span>
              <span className="text-sm text-muted-foreground">{p.description}</span>
            </ChoiceCard>
          ))}
        </div>
      )}
      <div
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={cn(
          'flex flex-col gap-2 rounded-xl border border-dashed p-4 transition-colors duration-150',
          dragging ? 'border-detect bg-detect/8' : 'border-input',
        )}
      >
        <span className="flex items-center gap-2 text-sm text-muted-foreground">
          <ImageUp aria-hidden className="size-4 shrink-0" />
          {file ? file.name : COPY.imageHint}
        </span>
        <TextField
          label="Ảnh"
          type="file"
          accept="image/jpeg,image/png"
          className="py-2"
          error={fileError ?? undefined}
          onChange={(e) => chooseFile(e.target.files?.[0])}
        />
      </div>
      {create.isError && <CreateError error={create.error} userId={me.data?.id} />}
      <div className="flex justify-end">
        <Button
          type="submit"
          size="lg"
          disabled={create.isPending || !model || !attack || (file !== null && !!imageError(file))}
        >
          {create.isPending ? COPY.submitting : COPY.submit}
        </Button>
      </div>
    </form>
  )
}

/** 429: lượt đang chạy (id nhớ ở trình duyệt, vì API không trả id); lỗi khác theo thông điệp chung. */
export function CreateError({ error, userId }: { error: unknown; userId: string | undefined }) {
  if (error instanceof ApiError && error.status === 429) {
    const last = userId ? lastQuickTry(userId) : null
    return (
      <FormAlert>
        {COPY.busy}{' '}
        {last ? (
          <Link
            to={`/quick-try?id=${last}`}
            className="font-semibold underline underline-offset-4"
            data-testid="quick-try-busy-link"
          >
            {COPY.busyLink}
          </Link>
        ) : (
          COPY.busyNoLink
        )}
      </FormAlert>
    )
  }
  return <FormAlert>{errorMessage(error)}</FormAlert>
}

export function QuickTryStatus({ id, onReset }: { id: string; onReset: () => void }) {
  const query = useQuickTry(id)
  if (query.isPending) return <PageLoading />
  if (query.isError) {
    const status = query.error instanceof ApiError ? query.error.status : null
    if (status === 410 || status === 404)
      return (
        <EmptyState
          icon={status === 410 ? Clock : SearchX}
          title={status === 410 ? COPY.gone : COPY.notFound}
          action={<Button onClick={onReset}>{COPY.retry}</Button>}
        >
          {status === 410 ? COPY.goneDetail : COPY.notFoundDetail}
        </EmptyState>
      )
    return <LoadError onRetry={() => void query.refetch()} retrying={query.isFetching} />
  }
  const view = query.data
  if (isPending(view))
    return (
      <section className="panel flex flex-col gap-3 p-5" aria-live="polite">
        <StatusBadge kind="tool_job" status={view.status} />
        <p className="text-sm text-muted-foreground">{COPY.pending}</p>
      </section>
    )
  if (view.status === 'failed')
    return (
      <section className="panel flex flex-col gap-3 p-5">
        <StatusBadge kind="tool_job" status="failed" />
        <FormAlert>
          {COPY.failed}: {view.error}
        </FormAlert>
        <div>
          <Button variant="outline" onClick={onReset}>
            {COPY.retry}
          </Button>
        </div>
      </section>
    )
  return <QuickTryResult view={view} />
}

/** Nhãn "Không phải kết quả kiểm thử" luôn ở đầu kết quả (`not_a_test_result`), màu ngưỡng. */
function NotATestResult({ expiresAt }: { expiresAt: string }) {
  return (
    <div
      data-testid="not-a-test-result"
      className="flex items-start gap-2 rounded-xl border border-threshold/40 bg-threshold/8 p-3 text-sm"
    >
      <TriangleAlert aria-hidden className="mt-0.5 size-4 shrink-0 text-threshold" />
      <div>
        <p className="font-semibold text-threshold">{COPY.notATestResult}</p>
        <p className="text-muted-foreground">{COPY.notATestResultDetail(expiryTime(expiresAt))}</p>
      </div>
    </div>
  )
}

function Pane({
  title,
  src,
  boxes,
  testId,
}: {
  title: string
  src: string | null
  boxes: BoxSet
  testId: string
}) {
  return (
    <figure className="flex min-w-0 flex-col gap-2">
      <figcaption className="text-sm font-semibold">{title}</figcaption>
      <div className="relative aspect-square w-full overflow-hidden bg-viewer-canvas">
        {src && (
          <img
            src={src}
            alt={title}
            data-testid={testId}
            draggable={false}
            className="absolute inset-0 size-full object-contain"
          />
        )}
        <BoxCanvas set={boxes} />
      </div>
    </figure>
  )
}

function LayerToggles({
  layers,
  onChange,
}: {
  layers: Record<QuickTryLayer, boolean>
  onChange: (next: Record<QuickTryLayer, boolean>) => void
}) {
  return (
    <div role="group" aria-label={COPY.layers} className="flex flex-wrap gap-2">
      {QUICK_TRY_LAYERS.map((key) => (
        <Button
          key={key}
          type="button"
          variant={layers[key] ? 'default' : 'outline'}
          aria-pressed={layers[key]}
          onClick={() => onChange({ ...layers, [key]: !layers[key] })}
        >
          <BoxSwatch kind={key} />
          {key === 'lost' ? `× ${COPY.layerLabels[key]}` : COPY.layerLabels[key]}
        </Button>
      ))}
    </div>
  )
}

function fmtScore(score: number | null): string {
  return score === null ? '—' : score.toFixed(2)
}

function ObjectTable({ level }: { level: QuickTryLevel }) {
  const t = COPY.table
  const counts = statusCounts(level)
  return (
    <div className="flex flex-col gap-3">
      <ul className="flex flex-wrap gap-2" aria-label="Số object theo trạng thái">
        {quickTryObjectStatusValues.map((status) => (
          <li key={status} className="flex items-center gap-1.5 text-sm tabular-nums">
            <StatusBadge kind="quick_try_object" status={status} />
            <span data-count={status}>{counts[status]}</span>
          </li>
        ))}
      </ul>
      <div data-testid="object-table" className="overflow-x-auto rounded-xl border border-border">
        <table className="w-full text-left text-sm">
          <caption className="sr-only">{t.caption}</caption>
          <thead className="bg-surface-raised text-xs text-muted-foreground">
            <tr>
              <th scope="col" className="px-3 py-2 font-semibold">
                {t.className}
              </th>
              <th scope="col" className="px-3 py-2 text-right font-semibold">
                {t.cleanScore}
              </th>
              <th scope="col" className="px-3 py-2 text-right font-semibold">
                {t.attackedScore}
              </th>
              <th scope="col" className="px-3 py-2 font-semibold">
                {t.status}
              </th>
            </tr>
          </thead>
          <tbody>
            {level.objects.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-3 py-4 text-muted-foreground">
                  {t.empty}
                </td>
              </tr>
            ) : (
              level.objects.map((o, i) => (
                <tr key={i} className="border-t border-border">
                  <td className="px-3 py-2">{o.class_name}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{fmtScore(o.clean_score)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {fmtScore(o.attacked_score)}
                  </td>
                  <td className="px-3 py-2">
                    <StatusBadge kind="quick_try_object" status={o.status} />
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

/**
 * Kết quả: ảnh sạch và ảnh tấn công cạnh nhau (điện thoại xếp dọc), thanh trượt level đổi ảnh và
 * bảng ngay trên dữ liệu đã tải, không gọi lại API.
 */
export function QuickTryResult({
  view,
  initialIndex = 0,
}: {
  view: QuickTryView
  initialIndex?: number
}) {
  const specs = useAttackSpecs()
  const [index, setIndex] = useState(initialIndex)
  const [layers, setLayers] = useState<Record<QuickTryLayer, boolean>>({ ...ALL_LAYERS })
  const level = view.levels[Math.min(index, view.levels.length - 1)]
  const param = specs.data?.find((s) => s.id === view.attack_spec_id)?.primary_param.name
  return (
    <section data-testid="quick-try-result" className="panel flex flex-col gap-4 p-5 md:p-6">
      <NotATestResult expiresAt={view.expires_at} />
      {level && (
        <>
          <div className="flex flex-col gap-2">
            {/* Không dùng <label>: chạm vào Term trong label sẽ chuyển focus sang thanh trượt và
                đóng tooltip; thanh trượt có tên qua aria-label. */}
            <p className="text-sm font-semibold">
              <Term term="level">{COPY.level}</Term>:{' '}
              <span className="tabular-nums">{levelText(level, param)}</span>
            </p>
            <input
              id="quick-try-level"
              type="range"
              min={0}
              max={view.levels.length - 1}
              step={1}
              value={index}
              aria-label={COPY.level}
              aria-valuetext={levelText(level, param)}
              onChange={(e) => setIndex(Number(e.target.value))}
              className="min-h-11 w-full accent-[var(--cta)]"
            />
          </div>
          <LayerToggles layers={layers} onChange={setLayers} />
          <div className="grid gap-4 md:grid-cols-2">
            <Pane
              title={COPY.clean}
              src={artifactSrc(view.clean_image_url)}
              boxes={cleanBoxes(level, layers)}
              testId="clean-image"
            />
            <Pane
              title={`${COPY.attacked} · ${levelText(level, param)}`}
              src={artifactSrc(level.image_url)}
              boxes={attackedBoxes(level, layers)}
              testId="attacked-image"
            />
          </div>
          <ObjectTable level={level} />
        </>
      )}
    </section>
  )
}
