import { Lock } from 'lucide-react'
import { type Dispatch, type ReactNode, useEffect, useRef } from 'react'

import type { AttackSpec, EstimateResponse } from '@/contracts/api'
import { cn } from '@/lib/utils'

import {
  defaultSearch,
  defaultTol,
  isDiscrete,
  searchErrors,
  SERVER_FIELD,
  SMALL_SUBSET,
  type SearchDraft,
  type SearchField,
  THRESHOLD_KINDS,
  withRange,
} from './search'
import { type Action, type AttackDraft, type AttackMode, searchCostSummary } from './state'

export const PATCH_SEARCH_LOCKED =
  'Tự tìm ngưỡng chưa hỗ trợ attack cần train patch: mỗi điểm đánh giá phải train một patch mới, chi phí quá lớn.'

const inputClass =
  'min-h-11 w-full rounded-[14px] border border-line bg-field text-foreground outline-none backdrop-blur transition-[border-color,box-shadow] duration-200 placeholder:text-muted-foreground/70 hover:border-input focus-visible:border-cta/70 focus-visible:ring-4 focus-visible:ring-cta/15 px-3 text-base aria-invalid:border-destructive'

function Field({
  id,
  label,
  error,
  hint,
  children,
}: {
  id: string
  label: string
  error?: string
  hint?: ReactNode
  children: ReactNode
}) {
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium">
        {label}
      </label>
      {children}
      {hint && <p className="text-sm text-muted-foreground">{hint}</p>}
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
    </div>
  )
}

/** Công tắc "Quét lưới / Tự tìm ngưỡng" của một attack (requirements.md Phase 7, wizard bước 4). */
export function ModeSwitch({
  spec,
  chosen,
  sliceSize,
  dispatch,
  protocolLocked = false,
}: {
  spec: AttackSpec
  chosen: AttackDraft
  sliceSize: number | null
  dispatch: Dispatch<Action>
  /** Phase 8: chế độ do protocol quy định (không đổi được). */
  protocolLocked?: boolean
}) {
  const locked = spec.requires_training === true
  const options: { mode: AttackMode; label: string }[] = [
    { mode: 'grid', label: 'Quét lưới' },
    { mode: 'search', label: 'Tự tìm ngưỡng' },
  ]
  return (
    <div className="space-y-1">
      <div
        role="radiogroup"
        aria-label={`Chế độ của ${spec.name}`}
        className="inline-flex flex-wrap gap-1 rounded-lg border p-1"
      >
        {options.map(({ mode, label }) => {
          const disabled = (locked && mode === 'search') || protocolLocked
          const selected = chosen.mode === mode
          return (
            <button
              key={mode}
              type="button"
              role="radio"
              aria-checked={selected}
              disabled={disabled}
              onClick={() =>
                dispatch({
                  type: 'mode',
                  attackSpecId: spec.id,
                  mode,
                  defaults: defaultSearch(spec.primary_param, sliceSize),
                })
              }
              className={cn(
                'min-h-11 rounded-md px-3 text-sm',
                selected ? 'bg-primary text-primary-foreground' : 'hover:bg-muted',
                disabled && 'cursor-not-allowed opacity-50',
              )}
            >
              {label}
            </button>
          )
        })}
      </div>
      {locked && (
        <p className="text-sm text-muted-foreground" data-testid="tim-nguong-khoa">
          {PATCH_SEARCH_LOCKED}
        </p>
      )}
    </div>
  )
}

/** Form tự tìm ngưỡng của một attack: lỗi `zod` ngay cạnh ô nhập, lỗi 422 của server theo đường
 * dẫn `attacks.<i>.search.<trường>`. */
export function SearchFields({
  spec,
  index,
  search,
  sliceSize,
  targetClasses,
  serverErrors,
  dispatch,
  onInputError,
  estimate,
  thresholdLocked = false,
}: {
  spec: AttackSpec
  index: number
  search: SearchDraft
  sliceSize: number | null
  targetClasses: string[] | null
  serverErrors: Record<string, string>
  dispatch: Dispatch<Action>
  onInputError: (bad: boolean) => void
  estimate?: EstimateResponse
  /** Phase 8: loại ngưỡng, ngưỡng, class do protocol quy định (khóa). */
  thresholdLocked?: boolean
}) {
  const param = spec.primary_param
  const discrete = isDiscrete(param)
  const errors = searchErrors(search, param, sliceSize, targetClasses)
  const bad = Object.keys(errors).length > 0
  // Wizard truyền callback mới mỗi lần render: chỉ báo khi trạng thái lỗi đổi.
  const report = useRef(onInputError)
  useEffect(() => {
    report.current = onInputError
  })
  useEffect(() => report.current(bad), [bad])

  const id = (name: string) => `tim-nguong-${spec.id}-${name}`
  const error = (field: SearchField) =>
    errors[field] ?? serverErrors[`attacks.${index}.search.${SERVER_FIELD[field]}`]
  const patch = (value: Partial<SearchDraft>) =>
    dispatch({ type: 'search', attackSpecId: spec.id, patch: value })
  const number = (raw: string) => (raw.trim() === '' ? Number.NaN : Number(raw))
  const setRange = (value: { lo?: number; hi?: number }) =>
    patch(withRange(search, value, discrete))
  const percent = Math.round(search.threshold * 100)
  const cost = estimate ? searchCostSummary(estimate, spec.id) : null
  const general =
    [serverErrors[`attacks.${index}.search`], serverErrors[`attacks.${index}.mode`]]
      .filter(Boolean)
      .join('; ') || undefined
  const unit = param.unit ? ` (${param.unit})` : ''

  return (
    <div className="space-y-4 rounded-lg bg-muted/40 p-3" data-testid={`tim-nguong-${spec.id}`}>
      {thresholdLocked && (
        <p
          className="flex items-center gap-2 text-sm text-muted-foreground"
          data-testid="nguong-khoa"
        >
          <Lock aria-hidden="true" className="size-4 shrink-0" />
          Loại ngưỡng, ngưỡng và class theo protocol; dải chỉ được rộng hơn, độ chính xác nhỏ hơn và
          số mẫu bootstrap nhiều hơn mức protocol yêu cầu.
        </p>
      )}
      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">Loại ngưỡng</legend>
        <div
          role="radiogroup"
          aria-label={`Loại ngưỡng của ${spec.name}`}
          className="grid gap-2 md:grid-cols-3"
        >
          {THRESHOLD_KINDS.map(({ kind, label, hint }) => (
            <button
              key={kind}
              type="button"
              role="radio"
              aria-checked={search.thresholdKind === kind}
              disabled={thresholdLocked}
              onClick={() => patch({ thresholdKind: kind })}
              className={cn(
                'flex min-h-11 flex-col items-start gap-1 rounded-lg border p-2 text-left',
                search.thresholdKind === kind
                  ? 'border-primary bg-primary/5 ring-2 ring-primary/30'
                  : 'hover:bg-muted',
                thresholdLocked && 'cursor-not-allowed opacity-70',
              )}
            >
              <span className="text-sm font-medium">{label}</span>
              <span className="text-xs text-muted-foreground">{hint}</span>
            </button>
          ))}
        </div>
      </fieldset>

      <Field id={id('threshold')} label="Ngưỡng (%)" error={error('threshold')}>
        <div className="flex items-center gap-3">
          <input
            type="range"
            min={1}
            max={100}
            step={1}
            aria-label={`Ngưỡng của ${spec.name} (thanh trượt)`}
            disabled={thresholdLocked}
            value={Number.isFinite(percent) ? percent : 1}
            onChange={(event) => patch({ threshold: Number(event.target.value) / 100 })}
            className="min-h-11 w-full min-w-0 flex-1"
          />
          <input
            id={id('threshold')}
            type="number"
            inputMode="decimal"
            min={1}
            max={100}
            value={Number.isFinite(percent) ? percent : ''}
            disabled={thresholdLocked}
            aria-invalid={error('threshold') ? true : undefined}
            onChange={(event) => patch({ threshold: number(event.target.value) / 100 })}
            className={cn(inputClass, 'w-24 shrink-0')}
          />
        </div>
      </Field>

      <Field
        id={id('class')}
        label="Class áp dụng (không bắt buộc)"
        error={error('classFilter')}
        hint="Bỏ trống: tính trên mọi class đích."
      >
        <select
          id={id('class')}
          value={search.classFilter ?? ''}
          disabled={thresholdLocked}
          onChange={(event) => patch({ classFilter: event.target.value || null })}
          className={inputClass}
        >
          <option value="">Mọi class</option>
          {(targetClasses ?? []).map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
      </Field>

      <div className="grid gap-3 md:grid-cols-3">
        {(['lo', 'hi'] as const).map((name) => (
          <Field
            key={name}
            id={id(name)}
            label={`${name === 'lo' ? 'Từ' : 'Đến'}${unit}`}
            error={error(name)}
          >
            {discrete ? (
              <select
                id={id(name)}
                value={search[name]}
                onChange={(event) => setRange({ [name]: Number(event.target.value) })}
                className={inputClass}
              >
                {(param.values ?? []).map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
              </select>
            ) : (
              <input
                id={id(name)}
                type="number"
                inputMode="decimal"
                step="any"
                value={Number.isFinite(search[name]) ? search[name] : ''}
                aria-invalid={error(name) ? true : undefined}
                onChange={(event) => setRange({ [name]: number(event.target.value) })}
                className={inputClass}
              />
            )}
          </Field>
        ))}
        {!discrete && (
          <Field
            id={id('tol')}
            label={`Độ chính xác${unit}`}
            error={error('tol')}
            hint={
              search.tolEdited
                ? `Mặc định (đến − từ) / 256 = ${defaultTol(search.lo, search.hi)}.`
                : 'Mặc định (đến − từ) / 256, tự tính lại khi đổi dải cho tới khi bạn sửa ô này.'
            }
          >
            <input
              id={id('tol')}
              type="number"
              inputMode="decimal"
              step="any"
              value={Number.isFinite(search.tol) ? search.tol : ''}
              aria-invalid={error('tol') ? true : undefined}
              onChange={(event) => patch({ tol: number(event.target.value), tolEdited: true })}
              className={inputClass}
            />
          </Field>
        )}
      </div>

      <details className="space-y-3">
        <summary className="min-h-11 cursor-pointer py-2 text-sm font-medium">Nâng cao</summary>
        <div className="grid gap-3 md:grid-cols-3">
          <Field id={id('coarse')} label="Số điểm quét thô" error={error('coarseN')}>
            <input
              id={id('coarse')}
              type="number"
              inputMode="numeric"
              min={3}
              max={8}
              value={Number.isFinite(search.coarseN) ? search.coarseN : ''}
              aria-invalid={error('coarseN') ? true : undefined}
              onChange={(event) => patch({ coarseN: number(event.target.value) })}
              className={inputClass}
            />
          </Field>
          <Field
            id={id('subset')}
            label="Kích thước tập con (ảnh)"
            error={error('subsetSize')}
            hint={
              Number.isFinite(search.subsetSize) && search.subsetSize < SMALL_SUBSET ? (
                <span className="text-threshold" data-testid="tap-con-nho">
                  Tập con dưới {SMALL_SUBSET} ảnh: điểm gãy trên tập con có thể lệch nhiều so với
                  toàn slice.
                </span>
              ) : (
                'Giai đoạn tìm kiếm chạy trên tập con; kết quả cuối xác nhận trên toàn slice.'
              )
            }
          >
            <input
              id={id('subset')}
              type="number"
              inputMode="numeric"
              min={2}
              max={sliceSize ?? undefined}
              value={Number.isFinite(search.subsetSize) ? search.subsetSize : ''}
              aria-invalid={error('subsetSize') ? true : undefined}
              onChange={(event) => patch({ subsetSize: number(event.target.value) })}
              className={inputClass}
            />
          </Field>
          <Field
            id={id('bootstrap')}
            label="Số mẫu bootstrap"
            error={error('bootstrapSamples')}
            hint="0 là không tính khoảng tin cậy."
          >
            <input
              id={id('bootstrap')}
              type="number"
              inputMode="numeric"
              min={0}
              max={1000}
              value={Number.isFinite(search.bootstrapSamples) ? search.bootstrapSamples : ''}
              aria-invalid={error('bootstrapSamples') ? true : undefined}
              onChange={(event) => patch({ bootstrapSamples: number(event.target.value) })}
              className={inputClass}
            />
          </Field>
        </div>
      </details>

      {general && (
        <p role="alert" className="text-sm text-destructive">
          {general}
        </p>
      )}
      {cost && (
        <p className="text-sm" data-testid={`chi-phi-toi-da-${spec.id}`}>
          {cost}
        </p>
      )}
    </div>
  )
}
