import { Activity, TriangleAlert } from 'lucide-react'

import { StatusBadge } from '@/components/status/StatusBadge'

import {
  attackName,
  conclusion,
  NEAR_THRESHOLD,
  NON_MONOTONIC,
  progressText,
  type SearchAttack,
  thresholdText,
} from './breakpoints'

function Warning({ icon: Icon, children }: { icon: typeof TriangleAlert; children: string }) {
  return (
    <p className="flex items-center gap-2 text-sm text-threshold">
      <Icon aria-hidden="true" className="size-4 shrink-0" />
      {children}
    </p>
  )
}

/** Thẻ tóm tắt điểm gãy của một attack (requirements.md Phase 7, Frontend: tab Kết quả). */
export function BreakpointCard({ attack }: { attack: SearchAttack }) {
  const { result } = attack
  const progress = progressText(result)
  return (
    <div className="flex min-w-0 flex-1 flex-col gap-2 text-left" data-attack={attack.attackSpecId}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-medium break-all">{attackName(attack)}</span>
        {result?.status ? (
          <StatusBadge kind="search" status={result.status} />
        ) : (
          <StatusBadge kind="run" status={result ? 'running' : 'queued'} />
        )}
      </div>
      <p className="font-medium" data-testid="ket-luan-diem-gay">
        {conclusion(attack)}
      </p>
      <p className="text-sm text-muted-foreground">{thresholdText(attack.config)}</p>
      {result?.near_threshold && <Warning icon={TriangleAlert}>{NEAR_THRESHOLD}</Warning>}
      {result?.status === 'non_monotonic' && <Warning icon={Activity}>{NON_MONOTONIC}</Warning>}
      {progress && (
        <p className="text-sm tabular-nums" data-testid="tien-do-tim-nguong">
          {progress}
        </p>
      )}
    </div>
  )
}
