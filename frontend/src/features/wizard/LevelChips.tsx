import { X } from 'lucide-react'
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
}

/** Chỉnh level bằng chip: nhập rồi Enter hoặc "Thêm"; kiểm tra dải và trùng ngay khi thêm. */
export function LevelChips({
  param,
  levels,
  onChange,
  serverError,
  onInputError,
}: LevelChipsProps) {
  const id = useId()
  const [text, setText] = useState('')
  const [error, setError] = useState<string | null>(null)

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
            <button
              type="button"
              className="-mr-2 inline-flex size-9 items-center justify-center rounded-full hover:bg-background"
              aria-label={`Bỏ level ${level}`}
              onClick={() => onChange(levels.filter((l) => l !== level))}
            >
              <X aria-hidden="true" className="size-4" />
            </button>
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
          className="min-h-11 w-full min-w-0 rounded-lg border border-input bg-background px-3 text-base outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 aria-invalid:border-destructive"
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
          onChange(presetLevels(param))
          report(null)
        }}
      >
        Dùng bộ gợi ý: {presetLevels(param).join(', ')}
      </Button>
    </div>
  )
}
