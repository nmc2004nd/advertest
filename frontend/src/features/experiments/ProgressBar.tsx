import type { Progress } from '@/contracts/api'

/** Thanh tiến độ ảnh đã xử lý (có chữ, không chỉ dựa vào màu). */
export function ProgressBar({ progress, label }: { progress: Progress; label?: string }) {
  const percent =
    progress.images_total > 0 ? Math.round((progress.images_done / progress.images_total) * 100) : 0
  const text = label ?? `${progress.images_done}/${progress.images_total} ảnh`
  return (
    <div className="flex min-w-0 items-center gap-2">
      <div
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        aria-label={text}
        className="h-2 min-w-16 flex-1 overflow-hidden rounded-full bg-muted"
      >
        <div className="h-full rounded-full bg-primary" style={{ width: `${percent}%` }} />
      </div>
      <span className="shrink-0 text-xs text-muted-foreground tabular-nums">{text}</span>
    </div>
  )
}
