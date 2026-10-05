import { Lock, X } from 'lucide-react'
import { useId, useState } from 'react'

import { Button } from '@/components/ui/button'
import type { PrimaryParam } from '@/contracts/api'

import { addLevel, levelError, parseLevel, presetLevels, rangeText } from './levels'

interface LevelChipsProps {
  param: PrimaryParam
  levels: number[]
  onChange: (levels: number[]) => void
  /** Lỗi từ server (422) cho các level của attack này. */
  serverError?: string
  /** Báo cho wizard biết ô đang có giá trị sai (chặn sang bước sau). */
  onInputError?: (hasError: boolean) => void
  /** Bộ level gợi ý (mặc định `presetLevels(param)`; patch dùng 0.1 và 0.25). */
  suggested?: number[]
  /** Phase 8: level bắt buộc theo protocol, không bỏ được. */
  lockedLevels?: number[]
}

/** Spec rời rạc (corruption: severity 1–5, Phase 6): mỗi giá trị một chip bật/tắt. */
function DiscreteChips({
  param,
  levels,
  onChange,
  serverError,
  lockedLevels = [],
}: Pick<LevelChipsProps, 'param' | 'levels' | 'onChange' | 'serverError' | 'lockedLevels'>) {
  const values = param.values ?? []
  return (
    <div className="space-y-2">
      <div role="group" aria-label={`Chọn ${param.name}`} className="flex flex-wrap gap-2">
        {values.map((value) => {
          const on = levels.includes(value)
          const locked = lockedLevels.includes(value)
          return (
            <Button
              key={value}
              type="button"
              variant={on ? 'default' : 'outline'}
              aria-pressed={on}
              disabled={locked}
              title={locked ? 'Level bắt buộc theo protocol' : undefined}
              className="min-w-11 tabular-nums"
              onClick={() =>
                onChange(on ? levels.filter((l) => l !== value) : addLevel(levels, value))
              }
            >
              {locked && <Lock aria-hidden="true" className="size-3" />}
              {value}
            </Button>
          )
        })}
      </div>
      <p className="text-sm text-muted-foreground">
        {param.name} ({rangeText(param)}): chọn một hoặc nhiều mức.
      </p>
      {serverError && (
        <p role="alert" className="text-sm text-destructive">
          {serverError}
        </p>
      )}
    </div>
  )
}

/** Chỉnh level bằng chip: nhập rồi Enter hoặc "Thêm"; kiểm tra dải và trùng ngay khi thêm. */
export function LevelChips({
  param,
  levels,
  onChange,
  serverError,
  onInputError,
  suggested,
  lockedLevels = [],
}: LevelChipsProps) {
  const id = useId()
  const [text, setText] = useState('')
  const [error, setError] = useState<string | null>(null)
  if (param.type === 'discrete' && param.values) {
    return (
      <DiscreteChips
        param={param}
        levels={levels}
        onChange={onChange}
        serverError={serverError}
        lockedLevels={lockedLevels}
      />
    )
  }
  const preset = suggested ?? presetLevels(param)

  const report = (message: string | null) => {
    setError(message)
    onInputError?.(message !== null)
  }

  const add = () => {
    const message = levelError(param, levels, text)
    if (message) return report(message)
    onChange(addLevel(levels, parseLevel(text)))
    setText('')
    report(null)
  }

  const shownError = error ?? serverError
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2" aria-label={`Level đã chọn (${param.name})`}>
        {levels.length === 0 && (
          <span className="text-sm text-muted-foreground">Chưa có level.</span>
        )}
        {levels.map((level) => (
          <span
            key={level}
            className="inline-flex min-h-11 items-center gap-1 rounded-full border bg-muted px-3 text-sm tabular-nums"
          >
            {level}
            {lockedLevels.includes(level) ? (
              <span
                className="-mr-1 inline-flex items-center"
                title="Level bắt buộc theo protocol"
                aria-label={`Level ${level} bắt buộc theo protocol`}
              >
                <Lock aria-hidden="true" className="size-4" />
              </span>
            ) : (
              <button
                type="button"
                className="-mr-2 inline-flex size-9 items-center justify-center rounded-full hover:bg-background"
                aria-label={`Bỏ level ${level}`}
                onClick={() => onChange(levels.filter((l) => l !== level))}
              >
                <X aria-hidden="true" className="size-4" />
              </button>
            )}
          </span>
        ))}
      </div>
      <label htmlFor={id} className="text-sm font-medium">
        Thêm level ({param.name}, {rangeText(param)})
      </label>
      <div className="flex gap-2">
        <input
          id={id}
          inputMode="decimal"
          placeholder={`Gõ một giá trị trong ${rangeText(param)} rồi Enter`}
          value={text}
          aria-invalid={shownError ? true : undefined}
          aria-describedby={shownError ? `${id}-loi` : undefined}
          onChange={(event) => {
            setText(event.target.value)
            if (error) report(null)
          }}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault()
              add()
            }
          }}
          className="min-h-11 w-full min-w-0 rounded-[14px] border border-line bg-field text-foreground outline-none backdrop-blur transition-[border-color,box-shadow] duration-200 placeholder:text-muted-foreground/70 hover:border-input focus-visible:border-cta/70 focus-visible:ring-4 focus-visible:ring-cta/15 px-3 text-base aria-invalid:border-destructive"
        />
        <Button type="button" variant="outline" onClick={add}>
          Thêm
        </Button>
      </div>
      {shownError && (
        <p id={`${id}-loi`} role="alert" className="text-sm text-destructive">
          {shownError}
        </p>
      )}
      <Button
        type="button"
        variant="outline"
        onClick={() => {
          onChange(preset)
          report(null)
        }}
      >
        Dùng bộ gợi ý: {preset.join(', ')}
      </Button>
    </div>
  )
}
