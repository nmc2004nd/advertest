import { CircleHelp } from 'lucide-react'
import { useId, useState } from 'react'

import { HOW_TO_READ } from '@/copy/charts'

/**
 * Câu kết luận một dòng phía trên biểu đồ và nút "Cách đọc" mở đoạn giải thích (requirements.md
 * Phase R3, Kết quả và insight). Đoạn giải thích luôn có trong DOM để `aria-controls` trỏ tới.
 */
export function ChartReading({
  sentence,
  reading,
  initialOpen = false,
}: {
  sentence: string
  reading: string
  /** Chỉ dùng cho test render tĩnh. */
  initialOpen?: boolean
}) {
  const id = useId()
  const [open, setOpen] = useState(initialOpen)
  return (
    <div className="space-y-1.5" data-testid="chart-reading">
      <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1">
        <p className="max-w-[72ch] min-w-0 flex-1 text-sm font-medium">{sentence}</p>
        <button
          type="button"
          aria-expanded={open}
          aria-controls={id}
          onClick={() => setOpen((value) => !value)}
          className="-my-2 inline-flex min-h-11 items-center gap-1.5 rounded-lg px-2 text-sm font-semibold text-cta hover:bg-muted focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
        >
          <CircleHelp className="size-4" aria-hidden />
          {HOW_TO_READ}
        </button>
      </div>
      <p
        id={id}
        hidden={!open}
        className="max-w-[72ch] rounded-lg bg-surface-raised px-3 py-2 text-sm text-muted-foreground"
      >
        {reading}
      </p>
    </div>
  )
}
