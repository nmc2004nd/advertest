import { ChevronLeft } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router'

/** Đầu trang (homepage-v2): eyebrow viên thuốc, tiêu đề lớn chữ khít, một câu mô tả, nút hành động. */
export function PageHeader({
  title,
  description,
  actions,
  back,
  eyebrow,
  size = 'default',
}: {
  title: ReactNode
  description?: ReactNode
  actions?: ReactNode
  back?: { to: string; label: string }
  /** Nhãn viên thuốc nhỏ phía trên tiêu đề. */
  eyebrow?: ReactNode
  /** `hero`: tiêu đề cỡ lớn cho trang chủ. */
  size?: 'default' | 'hero'
}) {
  return (
    <header className="flex flex-col gap-3">
      {back && (
        <Link
          to={back.to}
          className="-ml-1 inline-flex min-h-9 items-center gap-1 self-start rounded-full px-2 text-sm font-semibold text-muted-foreground hover:bg-secondary hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
        >
          <ChevronLeft className="size-4" aria-hidden />
          {back.label}
        </Link>
      )}
      {eyebrow && (
        <span className="text-[13px] font-semibold text-muted-foreground">{eyebrow}</span>
      )}
      <div className="flex flex-wrap items-end justify-between gap-5">
        <div className="flex min-w-0 flex-col gap-2.5">
          <h1
            className={
              size === 'hero'
                ? 'text-[clamp(1.9rem,2.8vw,2.5rem)] leading-[1.1] font-bold tracking-[-0.035em] break-words'
                : 'text-[clamp(1.6rem,2.2vw,2rem)] leading-[1.15] font-bold tracking-[-0.03em] break-words'
            }
          >
            {title}
          </h1>
          {description && (
            <p className="max-w-[64ch] text-[15px] leading-6 text-muted-foreground">
              {description}
            </p>
          )}
        </div>
        {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
      </div>
    </header>
  )
}

/** Tiêu đề khu vực: tiêu đề + một câu giải thích hoặc một hành động phụ bên phải. */
export function SectionTitle({
  title,
  detail,
  action,
  id,
}: {
  title: ReactNode
  detail?: ReactNode
  action?: ReactNode
  id?: string
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-x-4 gap-y-1">
      <h2 id={id} className="text-[17px] leading-6 font-semibold tracking-[-0.01em]">
        {title}
      </h2>
      {action ?? (detail && <p className="text-sm text-muted-foreground">{detail}</p>)}
    </div>
  )
}
