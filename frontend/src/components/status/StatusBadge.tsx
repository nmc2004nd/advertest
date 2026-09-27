import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

import { type StatusBadgeProps, statusDisplay, TONE_CLASS } from './status-config'

/** Trạng thái luôn hiển thị bằng màu + icon + chữ (tech-stack.md mục 5.1). */
export function StatusBadge(props: StatusBadgeProps) {
  const { label, icon: Icon, tone } = statusDisplay(props)
  return (
    <Badge
      className={cn('border-transparent', TONE_CLASS[tone])}
      data-kind={props.kind}
      data-status={props.status}
      data-tone={tone}
    >
      <Icon aria-hidden="true" data-icon="inline-start" />
      {label}
    </Badge>
  )
}
