import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

/**
 * Trạng thái trống (design.md mục 6): nói điều gì đang thiếu và nút hành động tiếp theo. Icon đặt
 * trong khung bounding box rỗng: "chưa phát hiện gì".
 */
export function EmptyState({
  icon: Icon,
  title,
  children,
  action,
}: {
  icon: LucideIcon
  title: string
  children?: ReactNode
  action?: ReactNode
}) {
  return (
    <div
      className="panel flex flex-col items-center gap-3 px-6 py-12 text-center"
      data-testid="trang-thai-trong"
    >
      <span className="bbox flex size-14 items-center justify-center text-detect-strong [--bbox-color:var(--detect)] [--bbox-size:12px]">
        <Icon className="size-6" aria-hidden />
      </span>
      <p className="text-[17px] font-bold">{title}</p>
      {children && <div className="max-w-md text-sm text-muted-foreground">{children}</div>}
      {action && <div className="mt-1 flex flex-wrap justify-center gap-2">{action}</div>}
    </div>
  )
}
