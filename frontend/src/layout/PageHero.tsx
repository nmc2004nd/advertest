import { ChevronLeft } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router'

import { FloatingDecor } from '@/components/background/FloatingDecor'
import { HERO_DECOR } from '@/components/background/decor-presets'
import { cn } from '@/lib/utils'

/**
 * Đầu trang có họa tiết (tham khảo beehiiv): nền tím nhạt, lưới lục giác mờ, các vòng tròn nét
 * đứt, ngôi sao gai; bên phải là minh họa viền mực riêng của trang. `compact` cho trang chi tiết:
 * thấp hơn, không có minh họa lớn. Minh họa ẩn trên điện thoại để chữ và nút lên trước.
 */
export function PageHero({
  title,
  description,
  actions,
  back,
  art,
  compact = false,
  children,
}: {
  title: ReactNode
  description?: ReactNode
  actions?: ReactNode
  back?: { to: string; label: string }
  art?: ReactNode
  compact?: boolean
  /** Nội dung phụ dưới mô tả (huy hiệu trạng thái, người chạy...). */
  children?: ReactNode
}) {
  return (
    <header
      className={cn(
        'hero relative isolate overflow-hidden rounded-[20px]',
        compact ? 'px-5 py-5 md:px-7' : 'px-5 py-7 md:px-9 md:py-9',
      )}
    >
      <HeroPattern compact={compact} />
      {!compact && <FloatingDecor items={HERO_DECOR} className="z-10 hidden lg:block" />}
      <div
        className={cn(
          'relative grid items-center gap-6',
          art && 'lg:grid-cols-[minmax(0,1fr)_auto] lg:gap-12',
        )}
      >
        <div className="flex min-w-0 flex-col gap-3">
          {back && (
            <Link
              to={back.to}
              className="-ml-1 inline-flex min-h-9 items-center gap-1 self-start rounded-full px-2 text-sm font-semibold text-muted-foreground hover:bg-white/70 hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
            >
              <ChevronLeft className="size-4" aria-hidden />
              {back.label}
            </Link>
          )}
          <h1
            className={cn(
              'font-bold tracking-[-0.035em] break-words text-foreground',
              compact
                ? 'text-[clamp(1.5rem,2vw,1.85rem)] leading-tight'
                : 'text-[clamp(1.85rem,2.6vw,2.5rem)] leading-[1.1]',
            )}
          >
            {title}
          </h1>
          {description && (
            <p className="max-w-[62ch] text-[15px] leading-6 text-muted-foreground">
              {description}
            </p>
          )}
          {children}
          {actions && <div className="mt-1 flex flex-wrap gap-2">{actions}</div>}
        </div>
        {art && (
          <div aria-hidden className="hidden pr-6 pb-6 lg:block">
            {art}
          </div>
        )}
      </div>
    </header>
  )
}

function HeroPattern({ compact }: { compact: boolean }) {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 -z-10">
      <div className="hero-hex absolute inset-0" />
      <svg
        className="absolute top-1/2 right-[8%] size-[560px] -translate-y-1/2"
        viewBox="0 0 560 560"
        fill="none"
      >
        {[110, 180, 250].map((r) => (
          <circle
            key={r}
            cx="280"
            cy="280"
            r={r}
            className="stroke-violet/30"
            strokeWidth="1.5"
            strokeDasharray="6 8"
          />
        ))}
      </svg>
      {compact && (
        <svg
          viewBox="0 0 100 100"
          className="absolute -top-8 -right-8 size-28 text-pink/70"
          fill="currentColor"
        >
          <path d="M50 0l7 33 26-21-16 30 33 8-33 8 16 30-26-21-7 33-7-33-26 21 16-30-33-8 33-8-16-30 26 21z" />
        </svg>
      )}
      {!compact && (
        <svg
          viewBox="0 0 120 12"
          className="absolute bottom-4 left-[38%] hidden h-3 w-28 lg:block"
          fill="none"
        >
          <path
            d="M2 6l6-4 6 8 6-8 6 8 6-8 6 8 6-8 6 8 6-8 6 8 6-8 6 8 6-8 6 8 6-8 6 8 6-8 6 8 4-3"
            className="stroke-violet/40"
            strokeWidth="1.6"
          />
        </svg>
      )}
    </div>
  )
}
