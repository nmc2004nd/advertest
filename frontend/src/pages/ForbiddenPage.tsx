import { ShieldAlert } from 'lucide-react'
import { Link } from 'react-router'

import { Button } from '@/components/ui/button'

export function ForbiddenPage() {
  return (
    <main className="mx-auto flex min-h-dvh max-w-md flex-col items-center justify-center gap-4 p-4 text-center">
      <ShieldAlert className="size-10 text-destructive" aria-hidden />
      <h1 className="text-xl font-semibold">Không có quyền truy cập</h1>
      <p className="text-muted-foreground">
        Tài khoản của bạn không có quyền xem trang này. Nếu cần quyền, hãy liên hệ quản trị viên.
      </p>
      <Button asChild>
        <Link to="/home">Về trang chủ</Link>
      </Button>
    </main>
  )
}
