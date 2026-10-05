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
        'flex items-start gap-2 rounded-md border p-3 text-sm',
        tone === 'error'
          ? 'border-fail/40 bg-fail/8 text-fail'
          : 'border-approved/40 bg-approved/8 text-approved',
      )}
    >
      <Icon className="mt-0.5 size-4 shrink-0" aria-hidden />
      <div>{children}</div>
    </div>
  )
}
