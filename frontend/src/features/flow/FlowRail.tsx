import { Check, ChevronRight } from 'lucide-react'
import { Link } from 'react-router'

import type { Role } from '@/contracts/api'
import { cn } from '@/lib/utils'

import { furthestActive, OWNER_LABEL, type StageView } from './flow'

/**
 * Quy trình của nhóm dạng checklist (tham khảo thẻ "Ready to launch" của beehiiv): thanh tiến độ
 * "bước X/7", mỗi bước một hàng có vòng trạng thái, người phụ trách và mũi tên nếu bấm được.
 * Bước đã qua có dấu ✓; bước đang chờ chính người dùng sáng hồng kèm nhãn "Bạn".
 */
export function FlowRail({
  stages,
  roles = [],
}: {
  stages: readonly StageView[]
  roles?: readonly Role[]
}) {
  const current = furthestActive(stages)
  const step = Math.max(0, current) + 1
  return (
    <section aria-labelledby="tieu-de-quy-trinh" className="panel flex flex-col gap-4 p-5">
      <div className="flex flex-col gap-1">
        <h2 id="tieu-de-quy-trinh" className="text-[16px] font-semibold">
          Quy trình của nhóm 🚀
        </h2>
        <p className="text-[13.5px] leading-5 text-muted-foreground">
          Kết luận chỉ chính thức sau khi một reviewer độc lập duyệt.
        </p>
      </div>
      <div className="flex items-center gap-3">
        <div
          className="h-2 flex-1 overflow-hidden rounded-full bg-muted"
          role="progressbar"
          aria-label="Tiến độ quy trình của nhóm"
          aria-valuemin={1}
          aria-valuemax={stages.length}
          aria-valuenow={step}
        >
          <div
            className="h-full rounded-full bg-gradient-to-r from-[#2563eb] via-[#7c3aed] to-[#ec4899] transition-[width] duration-700"
            style={{ width: `${(step / stages.length) * 100}%` }}
          />
        </div>
        <span className="text-[13px] font-semibold tabular-nums">
          {step}/{stages.length}
        </span>
      </div>
      <ol className="-mx-2 flex flex-col" data-testid="thanh-quy-trinh">
        {stages.map((stage, i) => (
          <Stage
            key={stage.id}
            stage={stage}
            passed={i < current}
            mine={stage.owner !== 'worker' && roles.includes(stage.owner)}
          />
        ))}
      </ol>
    </section>
  )
}

function Stage({ stage, passed, mine }: { stage: StageView; passed: boolean; mine: boolean }) {
  const action = stage.state === 'action'
  const active = stage.state === 'active'
  const body = (
    <>
      <span
        aria-hidden
        className={cn(
          'flex size-6 shrink-0 items-center justify-center rounded-full',
          passed
            ? 'bg-navy text-primary-foreground'
            : action
              ? 'border-2 border-pink bg-pink-soft'
              : active
                ? 'border-2 border-detect'
                : 'border-2 border-line',
        )}
      >
        {passed && <Check className="size-3.5" strokeWidth={3} />}
        {active && !passed && <span className="status-dot live size-2 text-detect" />}
        {action && !passed && <span className="size-2 rounded-full bg-pink" />}
      </span>
      <span className="flex min-w-0 flex-1 flex-col">
        <span className="flex items-center gap-2">
          <span className="truncate text-[14px] font-medium">{stage.title}</span>
          {mine && (
            <span className="rounded-full bg-pink-soft px-1.5 text-[11px] font-semibold text-[#be185d] dark:text-pink">
              Bạn
            </span>
          )}
        </span>
        <span
          className={cn(
            'truncate text-[12.5px]',
            action ? 'font-medium text-[#be185d] dark:text-pink' : 'text-muted-foreground',
          )}
        >
          {OWNER_LABEL[stage.owner]} · {stage.status}
        </span>
      </span>
      {stage.cta && (
        <ChevronRight
          className="size-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5"
          aria-hidden
        />
      )}
    </>
  )
  const row = cn(
    'group flex min-h-12 items-center gap-3 rounded-[10px] px-2 py-2',
    action && 'bg-pink-soft/70',
  )
  return (
    <li data-state={stage.state} data-stage={stage.id}>
      {stage.cta ? (
        <Link
          to={stage.cta.to}
          title={stage.cta.label}
          aria-label={`${stage.title}: ${stage.status}. ${stage.cta.label}`}
          className={cn(
            row,
            'transition-colors hover:bg-muted focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none',
          )}
        >
          {body}
        </Link>
      ) : (
        <div className={row}>{body}</div>
      )}
    </li>
  )
}
