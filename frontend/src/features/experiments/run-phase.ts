import type { RunView } from '@/contracts/api'

/** Giai đoạn của run đang chạy (Phase 6); null khi run không ở `running`. */
export function phaseText(run: RunView): string | null {
  if (run.phase === 'training') {
    return run.training
      ? `Đang train patch (${run.training.done}/${run.training.total})`
      : 'Đang train patch'
  }
  if (run.phase === 'evaluating') return 'Đang đánh giá'
  return null
}
