import { useId, type ComponentProps, type ReactNode } from 'react'

import { cn } from '@/lib/utils'

interface FieldShellProps {
  label: string
  /** Thông điệp lỗi hiển thị ngay dưới ô nhập. */
  error?: string
  hint?: string
  id?: string
  children: (control: {
    id: string
    'aria-invalid': true | undefined
    'aria-describedby': string | undefined
  }) => ReactNode
}

/** Nhãn, gợi ý, lỗi dùng chung cho mọi loại ô nhập; lỗi gắn với ô qua `aria-describedby`. */
function FieldShell({ label, error, hint, id, children }: FieldShellProps) {
  const autoId = useId()
  const inputId = id ?? autoId
  const hintId = `${inputId}-goi-y`
  const errorId = `${inputId}-loi`
  const describedBy = [hint && !error && hintId, error && errorId].filter(Boolean).join(' ')
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={inputId} className="text-[14px] font-semibold">
        {label}
      </label>
      {children({
        id: inputId,
        'aria-invalid': error ? true : undefined,
        'aria-describedby': describedBy || undefined,
      })}
      {hint && !error && (
        <p id={hintId} className="text-[13px] leading-5 text-muted-foreground">
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

// Font 16px (iOS không tự zoom khi chạm), cao ≥ 44px (tech-stack.md mục 5.1).
export const CONTROL_CLASS =
  'w-full rounded-[10px] border border-input bg-field px-3.5 text-base text-foreground shadow-[0_1px_2px_rgba(16,24,40,0.05)] transition-[border-color,box-shadow,background-color] duration-200 ease-out outline-none placeholder:text-muted-foreground/70 hover:border-muted-foreground focus-visible:border-violet focus-visible:ring-4 focus-visible:ring-violet/15 disabled:cursor-not-allowed disabled:opacity-60 aria-invalid:border-destructive aria-invalid:ring-destructive/20'

type ShellProps = Omit<FieldShellProps, 'children'>

/** Ô nhập một dòng có nhãn (requirements.md Phase 4, Hành vi chung). */
export function TextField({
  label,
  error,
  hint,
  id,
  className,
  ...props
}: ShellProps & ComponentProps<'input'>) {
  return (
    <FieldShell label={label} error={error} hint={hint} id={id}>
      {(control) => (
        <input {...control} className={cn(CONTROL_CLASS, 'min-h-11', className)} {...props} />
      )}
    </FieldShell>
  )
}

export function TextareaField({
  label,
  error,
  hint,
  id,
  className,
  ...props
}: ShellProps & ComponentProps<'textarea'>) {
  return (
    <FieldShell label={label} error={error} hint={hint} id={id}>
      {(control) => (
        <textarea
          rows={3}
          {...control}
          className={cn(CONTROL_CLASS, 'min-h-24 py-2', className)}
          {...props}
        />
      )}
    </FieldShell>
  )
}

export function SelectField({
  label,
  error,
  hint,
  id,
  className,
  children,
  ...props
}: ShellProps & ComponentProps<'select'>) {
  return (
    <FieldShell label={label} error={error} hint={hint} id={id}>
      {(control) => (
        <select {...control} className={cn(CONTROL_CLASS, 'min-h-11', className)} {...props}>
          {children}
        </select>
      )}
    </FieldShell>
  )
}
