import { Check, Plus } from 'lucide-react'
import { useState } from 'react'

import { CONTROL_CLASS } from '@/components/form/TextField'
import { Button } from '@/components/ui/button'
import type { AttackSpec } from '@/contracts/api'
import { levelCandidates, levelInputError, rangeText } from '@/features/wizard/levels'
import { cn } from '@/lib/utils'

import { formatLevels, parseLevels } from './form'

const CHIP =
  'inline-flex min-h-11 min-w-11 items-center justify-center gap-1.5 rounded-full border px-3.5 text-sm tabular-nums transition-colors duration-150 focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none'
const CHIP_ON = 'border-navy bg-navy text-primary-foreground'
const CHIP_OFF = 'border-line bg-surface-solid hover:border-input'

/**
 * Level bắt buộc của attack quét lưới: bấm chip để bật/tắt (level gợi ý trong dải của spec), gõ
 * một giá trị rồi Enter hoặc "Thêm" để thêm level khác. Form vẫn lưu chuỗi ngăn bởi dấu phẩy.
 */
export function AttackLevelChips({
  idBase,
  spec,
  value,
  error,
  onChange,
}: {
  idBase: string
  spec: AttackSpec | undefined
  value: string
  error?: string
  onChange: (levels: string) => void
}) {
  const [text, setText] = useState('')
  const [local, setLocal] = useState<string | null>(null)
  const labelId = `${idBase}-level-nhan`
  const inputId = `${idBase}-level-them`
  const levels = parseLevels(value)
  const shown = local ?? error

  if (!spec) {
    return (
      <div className="space-y-1.5">
        <p className="text-[14px] font-semibold">Level bắt buộc</p>
        <p className="text-[13px] leading-5 text-muted-foreground">
          Chọn attack trước để thấy các level gợi ý.
        </p>
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}
      </div>
    )
  }

  const param = spec.primary_param
  const discrete = param.type === 'discrete' && Boolean(param.values)
  const candidates = levelCandidates(spec, levels)
  const add = () => {
    const message = levelInputError(param, levels, text)
    if (message) return setLocal(message)
    onChange(formatLevels([...levels, Number(text.trim().replace(',', '.'))]))
    setText('')
    setLocal(null)
  }

  return (
    <div className="space-y-2">
      <p id={labelId} className="text-[14px] font-semibold">
        Level bắt buộc
      </p>
      <div role="group" aria-labelledby={labelId} className="flex flex-wrap gap-2">
        {candidates.map((v) => {
          const on = levels.includes(v)
          return (
            <button
              key={v}
              type="button"
              aria-pressed={on}
              aria-label={`Level ${v}`}
              onClick={() => {
                setLocal(null)
                onChange(formatLevels(on ? levels.filter((l) => l !== v) : [...levels, v]))
              }}
              className={cn(CHIP, on ? CHIP_ON : CHIP_OFF)}
            >
              {on && <Check aria-hidden="true" className="size-3.5" />}
              {v}
            </button>
          )
        })}
      </div>
      {!discrete && (
        <div className="flex max-w-md flex-col gap-1.5">
          <label htmlFor={inputId} className="text-sm font-medium">
            Thêm level khác ({rangeText(param)})
          </label>
          <div className="flex gap-2">
            <input
              id={inputId}
              inputMode="decimal"
              placeholder="Gõ rồi Enter"
              value={text}
              aria-invalid={local ? true : undefined}
              onChange={(e) => {
                setText(e.target.value)
                setLocal(null)
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault()
                  add()
                }
              }}
              className={cn(CONTROL_CLASS, 'min-h-11')}
            />
            <Button type="button" variant="outline" onClick={add}>
              <Plus aria-hidden="true" />
              Thêm
            </Button>
          </div>
        </div>
      )}
      <p className="text-[13px] leading-5 text-muted-foreground">
        {param.name} ({rangeText(param)}): bấm để chọn một hoặc nhiều level.
      </p>
      {shown && (
        <p role="alert" className="text-sm text-destructive">
          {shown}
        </p>
      )}
    </div>
  )
}

/** Level của tiêu chí mức sụt: chọn đúng một trong các level bắt buộc của attack. */
export function CriterionLevelChips({
  idBase,
  levels,
  value,
  error,
  onChange,
}: {
  idBase: string
  levels: number[]
  value: string
  error?: string
  onChange: (level: string) => void
}) {
  const labelId = `${idBase}-level-nhan`
  return (
    <div className="space-y-2 md:col-span-2">
      <p id={labelId} className="text-[14px] font-semibold">
        Level
      </p>
      {levels.length === 0 ? (
        <p className="text-[13px] leading-5 text-muted-foreground">
          Chọn attack có level bắt buộc trước.
        </p>
      ) : (
        <div role="radiogroup" aria-labelledby={labelId} className="flex flex-wrap gap-2">
          {levels.map((v) => {
            const on = value.trim() !== '' && Number(value) === v
            return (
              <button
                key={v}
                type="button"
                role="radio"
                aria-checked={on}
                onClick={() => onChange(String(v))}
                className={cn(CHIP, on ? CHIP_ON : CHIP_OFF)}
              >
                {v}
              </button>
            )
          })}
        </div>
      )}
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
    </div>
  )
}
