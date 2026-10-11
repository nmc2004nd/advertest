import { Circle, CircleCheck, CircleDot, CircleX, type LucideIcon, PencilLine } from 'lucide-react'

import { cn } from '@/lib/utils'

import type { LifecycleState, LifecycleStep } from './lifecycle'

const ICON: Record<LifecycleState, LucideIcon> = {
  done: CircleCheck,
  current: CircleDot,
  todo: Circle,
  failed: CircleX,
}

// Cùng tông với StatusBadge (design.md mục 3): xong = success, đang làm = info, lỗi = danger.
const TONE: Record<LifecycleState, string> = {
  done: 'text-approved',
  current: 'text-detect',
  todo: 'text-muted-foreground',
  failed: 'text-fail',
}

const STATE_LABEL: Record<LifecycleState, string> = {
  done: 'xong',
  current: 'đang làm',
  todo: 'chưa tới',
  failed: 'có lỗi',
}

/** Thanh vòng đời: mỗi bước màu + icon + chữ (mission.md nguyên tắc 6). */
export function Lifecycle({ steps }: { steps: LifecycleStep[] }) {
  return (
    <ol
      data-testid="lifecycle"
      aria-label="Vòng đời experiment"
      className={cn(
        'grid gap-2',
        steps.length > 3 ? 'grid-cols-2 sm:grid-cols-3 lg:grid-cols-6' : 'grid-cols-3',
      )}
    >
      {steps.map((s) => {
        const Icon = s.warning ? PencilLine : ICON[s.state]
        return (
          <li
            key={s.id}
            data-testid="lifecycle-step"
            data-step={s.id}
            data-state={s.state}
            aria-current={s.state === 'current' ? 'step' : undefined}
            className={cn(
              'flex min-w-0 items-start gap-2 rounded-[10px] border px-3 py-2',
              s.state === 'current'
                ? 'border-detect/40 bg-detect/[0.06]'
                : 'border-line bg-surface-solid/70',
            )}
          >
            <Icon
              aria-hidden="true"
              className={cn('mt-0.5 size-4 shrink-0', s.warning ? 'text-threshold' : TONE[s.state])}
            />
            <span className="flex min-w-0 flex-col">
              <span className="text-sm font-semibold">
                {s.label}
                <span className="sr-only">: {STATE_LABEL[s.state]}</span>
              </span>
              <span
                className={cn(
                  'text-xs leading-4',
                  s.state === 'failed'
                    ? s.warning
                      ? 'text-threshold'
                      : 'text-fail'
                    : 'text-muted-foreground',
                )}
              >
                {s.detail}
              </span>
            </span>
          </li>
        )
      })}
    </ol>
  )
}
