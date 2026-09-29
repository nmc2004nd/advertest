import { CircleAlert, CircleCheck } from 'lucide-react'
import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

/** Thông báo cấp form (lỗi chung hoặc thành công), đọc được bằng trình đọc màn hình. */
export function FormAlert({
  tone = 'error',
  children,
}: {
  tone?: 'error' | 'success'
  children: ReactNode
}) {
  const Icon = tone === 'error' ? CircleAlert : CircleCheck
  return (
    <div
      role={tone === 'error' ? 'alert' : 'status'}
      className={cn(
        'flex items-start gap-2 rounded-lg border p-3 text-sm',
        tone === 'error'
          ? 'border-destructive/40 bg-destructive/5 text-destructive'
          : 'border-emerald-600/40 bg-emerald-600/5 text-emerald-800 dark:text-emerald-300',
      )}
    >
      <Icon className="mt-0.5 size-4 shrink-0" aria-hidden />
      <div>{children}</div>
    </div>
  )
}
