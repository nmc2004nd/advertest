import type { ExperimentSummary } from '@/contracts/api'

import { ACTIVE_EXPERIMENT } from './api'

export const RECENT_FINISHED = 5

/** Chia experiment của tôi: đang chạy hoặc chờ; 5 cái kết thúc gần nhất (theo finished_at). */
export function splitMine(items: ExperimentSummary[]): {
  active: ExperimentSummary[]
  finished: ExperimentSummary[]
} {
  const active = items.filter((e) => ACTIVE_EXPERIMENT.includes(e.status))
  const finished = items
    .filter((e) => e.finished_at !== null)
    .sort((a, b) => (b.finished_at ?? '').localeCompare(a.finished_at ?? ''))
    .slice(0, RECENT_FINISHED)
  return { active, finished }
}
