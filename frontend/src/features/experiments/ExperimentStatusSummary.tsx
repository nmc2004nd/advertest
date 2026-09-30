import { StatusBadge } from '@/components/status/StatusBadge'
import type { ExperimentSummary } from '@/contracts/api'

import { statusSentence } from './status-sentence'

/** Trạng thái tổng hợp của experiment: badge + câu tóm tắt số run (mission.md nguyên tắc 6). */
export function ExperimentStatusSummary({ experiment }: { experiment: ExperimentSummary }) {
  return (
    <div className="flex min-w-0 flex-wrap items-center gap-2">
      <StatusBadge kind="experiment" status={experiment.status} />
      <span className="text-sm text-muted-foreground">{statusSentence(experiment.run_counts)}</span>
    </div>
  )
}
