import { ChevronDown } from 'lucide-react'
import { type ReactNode, useEffect, useId, useRef, useState } from 'react'

import { cn } from '@/lib/utils'

/**
 * Section thu gọn được ở cuối tab Tổng quan (requirements.md Phase R3: tab Chi phí và Tái lập cũ).
 * Mẫu accordion: nút nằm trong heading. Nội dung chỉ render khi mở (Tái lập tải manifest từng run).
 * `scrollTo`: mở từ `?tab=` cũ; cuộn tới section một lần, khi nó chuyển sang true (trang truyền true
 * sau khi phần phía trên đã tải xong để vị trí không bị đẩy xuống).
 */
export function OverviewSection({
  title,
  defaultOpen = false,
  scrollTo = false,
  children,
}: {
  title: string
  defaultOpen?: boolean
  scrollTo?: boolean
  children: ReactNode
}) {
  const [open, setOpen] = useState(defaultOpen)
  const ref = useRef<HTMLElement>(null)
  const scrolled = useRef(false)
  const id = useId()

  useEffect(() => {
    if (!scrollTo || scrolled.current) return
    scrolled.current = true
    ref.current?.scrollIntoView({ block: 'start' })
  }, [scrollTo])

  return (
    <section ref={ref} className="panel scroll-mt-4" aria-labelledby={`${id}-h`}>
      <h2 id={`${id}-h`} className="text-[17px] leading-6 font-semibold tracking-[-0.01em]">
        <button
          type="button"
          aria-expanded={open}
          aria-controls={`${id}-c`}
          onClick={() => setOpen((v) => !v)}
          className="flex min-h-11 w-full items-center justify-between gap-3 rounded-xl px-5 py-3 text-left focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
        >
          {title}
          <ChevronDown
            aria-hidden="true"
            className={cn(
              'size-4 shrink-0 text-muted-foreground transition-transform duration-200 motion-reduce:transition-none',
              open && 'rotate-180',
            )}
          />
        </button>
      </h2>
      <div id={`${id}-c`} hidden={!open} className="min-w-0 border-t border-line px-5 py-4">
        {open && children}
      </div>
    </section>
  )
}
