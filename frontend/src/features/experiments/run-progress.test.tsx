import { describe, expect, it } from 'vitest'

import { listMocks } from '@/api/mocks'
import type { RunView } from '@/contracts/api'
import { render } from '@/test-utils'

import { phaseText } from './run-phase'
import { RunProgress } from './RunProgress'

const runs = listMocks<RunView>('run_view')
const training = runs.find((r) => r.phase === 'training')
const evaluating = runs.find((r) => r.phase === 'evaluating')

describe('tiến độ hai giai đoạn của run patch (Phase 6, task 33)', () => {
  it('đang train: số vòng lặp, thanh theo vòng', () => {
    if (!training?.training) throw new Error('Thiếu mock run đang train')
    const { done, total } = training.training
    expect(phaseText(training)).toBe(`Đang train patch (${done}/${total})`)
    const html = render(<RunProgress run={training} />)
    expect(html).toContain(`Đang train patch (${done}/${total})`)
    expect(html).toContain(`aria-valuenow="${Math.round((done / total) * 100)}"`)
    expect(html).toContain(`${done}/${total} vòng`)
  })

  it('đang đánh giá: thanh theo ảnh', () => {
    if (!evaluating) throw new Error('Thiếu mock run đang đánh giá')
    const html = render(<RunProgress run={evaluating} />)
    expect(html).toContain('Đang đánh giá')
    expect(html).toContain(
      `${evaluating.progress.images_done}/${evaluating.progress.images_total} ảnh`,
    )
  })

  it('run không chạy: không có nhãn giai đoạn', () => {
    const done = runs.find((r) => r.status === 'completed')
    if (!done) throw new Error('Thiếu mock run xong')
    expect(phaseText(done)).toBeNull()
    expect(render(<RunProgress run={done} />)).not.toContain('Đang ')
  })
})
