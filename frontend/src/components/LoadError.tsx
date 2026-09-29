import { CircleAlert } from 'lucide-react'

import { Button } from '@/components/ui/button'

/** Không tải được dữ liệu (lỗi server, mất mạng): thông báo và nút thử lại. */
export function LoadError({
  onRetry,
  retrying = false,
}: {
  onRetry: () => void
  retrying?: boolean
}) {
  return (
    <div role="alert" className="flex min-h-40 flex-col items-center justify-center gap-3 p-6">
      <CircleAlert className="size-6 text-destructive" aria-hidden />
      <p>Không tải được dữ liệu. Kiểm tra kết nối rồi thử lại.</p>
      <Button variant="outline" onClick={onRetry} disabled={retrying}>
        {retrying ? 'Đang thử lại…' : 'Thử lại'}
      </Button>
    </div>
  )
}
