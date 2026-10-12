import { Plus } from 'lucide-react'
import { useId, useState } from 'react'

import { CONTROL_CLASS } from '@/components/form/TextField'
import { Button } from '@/components/ui/button'
import type { PrimaryParam } from '@/contracts/api'
import { cn } from '@/lib/utils'

import { addLevel, levelInputError, rangeText } from './levels'

/**
 * Gõ thêm một level ngoài các chip gợi ý (chỉ trong "Tùy chỉnh nâng cao", requirements.md Phase R3:
 * ô số chỉ nằm trong phần nâng cao). Kiểm tra dải, trùng và tối đa level ngay khi thêm.
 */
export function CustomLevel({
  param,
  levels,
  onChange,
}: {
  param: PrimaryParam
  levels: number[]
  onChange: (levels: number[]) => void
}) {
  const id = useId()
  const [text, setText] = useState('')
  const [error, setError] = useState<string | null>(null)
  const add = () => {
    const message = levelInputError(param, levels, text)
    if (message) return setError(message)
    onChange(addLevel(levels, Number(text.trim().replace(',', '.'))))
    setText('')
    setError(null)
  }
  return (
    <div className="flex max-w-md flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium">
        Thêm level khác ({param.name}, {rangeText(param)})
      </label>
      <div className="flex gap-2">
        <input
          id={id}
          inputMode="decimal"
          placeholder="Gõ rồi Enter"
          value={text}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${id}-loi` : undefined}
          onChange={(e) => {
            setText(e.target.value)
            setError(null)
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
      {error && (
        <p id={`${id}-loi`} role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
    </div>
  )
}
