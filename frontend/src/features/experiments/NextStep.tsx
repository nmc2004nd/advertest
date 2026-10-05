import { Lock } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router'

import { Button } from '@/components/ui/button'
import type { ExperimentDetail } from '@/contracts/api'
import { cn } from '@/lib/utils'

import type { NextStepView, Tone } from './next-step'
import { lockedBannerText } from './review-labels'

const TONE: Record<Tone, string> = {
  info: 'border-detect/40 bg-detect/[0.06]',
  action: 'border-detect-strong/40 bg-accent/60',
  success: 'border-approved/40 bg-approved/[0.07]',
  warning: 'border-threshold/45 bg-threshold/[0.08]',
  danger: 'border-fail/40 bg-fail/[0.06]',
  muted: 'border-line bg-surface-raised',
}

/** Khối "bước tiếp theo" ở đầu trang chi tiết; gồm cả dải "Đã khóa" khi đã gửi duyệt. */
export function NextStepPanel({
  experiment,
  view,
  onSubmit,
  extra,
}: {
  experiment: ExperimentDetail
  view: NextStepView | null
  onSubmit: () => void
  extra?: ReactNode
}) {
  const banner = lockedBannerText(experiment.status)
  if (!view && !banner) return null
  return (
    <div
      className={cn(
        'flex flex-col gap-3 rounded-xl border p-5',
        view ? TONE[view.tone] : TONE.muted,
      )}
      data-testid="buoc-tiep-theo"
    >
      {banner && (
        <p
          role="status"
          className="flex items-center gap-2 text-sm font-medium"
          data-testid="dai-khoa"
        >
          <Lock aria-hidden="true" className="size-4 shrink-0" />
          {banner}
        </p>
      )}
      {view && (
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div className="flex flex-col gap-1">
            <p className="text-[17px] font-semibold">{view.title}</p>
            <p className="max-w-[68ch] text-[15px] leading-6 text-muted-foreground">{view.body}</p>
          </div>
          <div className="flex shrink-0 flex-wrap gap-2">
            {view.secondary && (
              <Button asChild variant="outline">
                <Link to={view.secondary.to}>{view.secondary.label}</Link>
              </Button>
            )}
            {view.primary &&
              (view.primary.onClick ? (
                <Button onClick={onSubmit}>{view.primary.label}</Button>
              ) : (
                <Button asChild>
                  <Link to={view.primary.to ?? '#'}>{view.primary.label}</Link>
                </Button>
              ))}
            {extra}
          </div>
        </div>
      )}
    </div>
  )
}
