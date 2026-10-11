import type { ReactNode } from 'react'

import { type DecisionKey, DECISIONS } from '@/copy/decisions'
import { cn } from '@/lib/utils'

/**
 * Bảng ý nghĩa quyết định (requirements.md Phase R3, mục Ý nghĩa quyết định): mỗi quyết định 3
 * dòng — điều gì xảy ra ngay, ai làm bước tiếp theo, có đảo ngược được không.
 */
export function DecisionMeaning({
  decisions,
  highlight = null,
  title,
  children,
  className,
}: {
  decisions: DecisionKey[]
  /** Quyết định đang chọn: dòng của nó được nhấn. */
  highlight?: DecisionKey | null
  title?: string
  /** Nội dung đặt trước các quyết định (ví dụ verdict trên trang report). */
  children?: ReactNode
  className?: string
}) {
  const many = decisions.length > 1
  return (
    <div
      data-testid="decision-meaning"
      className={cn(
        'flex flex-col gap-2 rounded-[10px] border border-line bg-surface-raised/60 p-3 text-sm',
        className,
      )}
    >
      {title && <p className="font-semibold">{title}</p>}
      {children}
      {decisions.map((key) => {
        const d = DECISIONS[key]
        const active = highlight === key
        return (
          <div
            key={key}
            data-decision={key}
            data-active={active || undefined}
            className={cn(
              'flex flex-col gap-1 rounded-lg transition-colors duration-150 motion-reduce:transition-none',
              many && 'border border-transparent p-2',
              active && 'border-cta/50 bg-cta/[0.06]',
            )}
          >
            {many && <p className="font-semibold">{d.label}</p>}
            <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-0.5 leading-5">
              <dt className="text-muted-foreground">Ngay sau đó</dt>
              <dd>{d.now}</dd>
              <dt className="text-muted-foreground">Tiếp theo</dt>
              <dd>{d.next}</dd>
              <dt className="text-muted-foreground">Đảo ngược</dt>
              <dd>{d.reversible}</dd>
            </dl>
          </div>
        )
      })}
    </div>
  )
}
