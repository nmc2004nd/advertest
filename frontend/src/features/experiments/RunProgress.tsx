import type { RunView } from '@/contracts/api'

import { ProgressBar } from './ProgressBar'
import { phaseText } from './run-phase'

/**
 * Tiến độ của một run (requirements.md Phase 6, Frontend): run patch hiện "Đang train patch (x/y)"
 * với thanh theo vòng lặp, rồi "Đang đánh giá" với thanh theo ảnh.
 */
export function RunProgress({ run }: { run: RunView }) {
  const phase = phaseText(run)
  if (run.phase === 'training' && run.training) {
    return (
      <div className="space-y-1">
        <p className="text-xs font-medium">{phase}</p>
        <ProgressBar
          progress={{ images_done: run.training.done, images_total: run.training.total }}
          label={`${run.training.done}/${run.training.total} vòng`}
        />
      </div>
    )
  }
  return (
    <div className="space-y-1">
      {phase && <p className="text-xs font-medium">{phase}</p>}
      <ProgressBar progress={run.progress} />
    </div>
  )
}
