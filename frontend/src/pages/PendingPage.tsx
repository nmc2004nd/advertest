import { Link, useSearchParams } from 'react-router'

import { pendingScreen } from '@/auth/pending-screens'
import { Button } from '@/components/ui/button'
import { PublicLayout } from '@/layout/PublicLayout'

export function PendingPage() {
  const [params] = useSearchParams()
  const screen = pendingScreen(params.get('code'))
  const Icon = screen.icon
  return (
    <PublicLayout title={screen.title}>
      <div className="flex items-start gap-3">
        <Icon className="mt-0.5 size-6 shrink-0 text-muted-foreground" aria-hidden />
        <p className="text-muted-foreground">{screen.body}</p>
      </div>
      <Button asChild variant="outline">
        <Link to="/login">Về trang đăng nhập</Link>
      </Button>
    </PublicLayout>
  )
}
