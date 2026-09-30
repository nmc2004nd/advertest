import { Link } from 'react-router'

import { StatusBadge } from '@/components/status/StatusBadge'
import { Button } from '@/components/ui/button'
import type { ExperimentSummary } from '@/contracts/api'

import { useMyRecentExperiments } from './api'
import { timeText } from './format'
import { splitMine } from './home'
import { ProgressBar } from './ProgressBar'

function Item({ experiment, progress }: { experiment: ExperimentSummary; progress?: boolean }) {
  return (
    <li>
      <Link
        to={`/experiments/${experiment.id}`}
        className="flex flex-col gap-1 rounded-lg p-2 hover:bg-muted focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
      >
        <span className="flex flex-wrap items-center gap-2">
          <span className="min-w-0 font-medium break-all">{experiment.name}</span>
          <StatusBadge kind="experiment" status={experiment.status} />
        </span>
        {progress ? (
          <ProgressBar progress={experiment.progress} />
        ) : (
          <span className="text-xs text-muted-foreground">{timeText(experiment)}</span>
        )}
      </Link>
    </li>
  )
}

/** Khối engineer trên /home (requirements.md Phase 5, Trang chủ). */
export function EngineerHome() {
  const query = useMyRecentExperiments()
  const { active, finished } = splitMine(query.data?.items ?? [])
  return (
    <div className="flex flex-col gap-3">
      <Button asChild className="self-start">
        <Link to="/experiments/new">Tạo experiment</Link>
      </Button>
      {query.isPending ? (
        <p className="text-muted-foreground">Đang tải…</p>
      ) : query.isError ? (
        <p className="text-destructive">Không tải được experiment của bạn.</p>
      ) : (
        <>
          <div>
            <h3 className="text-sm font-medium">Đang chạy hoặc chờ</h3>
            {active.length === 0 ? (
              <p className="text-sm text-muted-foreground">Không có experiment nào đang chạy.</p>
            ) : (
              <ul>
                {active.map((e) => (
                  <Item key={e.id} experiment={e} progress />
                ))}
              </ul>
            )}
          </div>
          <div>
            <h3 className="text-sm font-medium">Kết thúc gần đây</h3>
            {finished.length === 0 ? (
              <p className="text-sm text-muted-foreground">Chưa có experiment nào kết thúc.</p>
            ) : (
              <ul>
                {finished.map((e) => (
                  <Item key={e.id} experiment={e} />
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </div>
  )
}
