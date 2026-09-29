import { LoaderCircle } from 'lucide-react'

export function PageLoading() {
  return (
    <div role="status" className="flex min-h-40 items-center justify-center gap-2 p-6">
      <LoaderCircle className="size-5 animate-spin" aria-hidden />
      <span className="text-sm text-muted-foreground">Đang tải…</span>
    </div>
  )
}
