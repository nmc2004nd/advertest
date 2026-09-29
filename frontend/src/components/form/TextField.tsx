import { useId, type ComponentProps } from 'react'

import { cn } from '@/lib/utils'

interface TextFieldProps extends ComponentProps<'input'> {
  label: string
  /** Thông điệp lỗi hiển thị ngay dưới ô nhập. */
  error?: string
  hint?: string
}

/**
 * Ô nhập có nhãn; font 16px (iOS không tự zoom), cao ≥ 44px; lỗi gắn với ô qua
 * `aria-describedby` và `aria-invalid` (requirements.md Phase 4, Hành vi chung).
 */
export function TextField({ label, error, hint, id, className, ...props }: TextFieldProps) {
  const autoId = useId()
  const inputId = id ?? autoId
  const hintId = `${inputId}-goi-y`
  const errorId = `${inputId}-loi`
  const describedBy = [hint && hintId, error && errorId].filter(Boolean).join(' ') || undefined
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={inputId} className="text-sm font-medium">
        {label}
      </label>
      <input
        id={inputId}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        className={cn(
          'min-h-11 w-full rounded-lg border border-input bg-background px-3 text-base outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 aria-invalid:border-destructive aria-invalid:ring-destructive/20',
          className,
        )}
        {...props}
      />
      {hint && !error && (
        <p id={hintId} className="text-sm text-muted-foreground">
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
    </div>
  )
}
