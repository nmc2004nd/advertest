// validation.md Phase R3, Group 5: bấm điểm yếu mở Failure case đã lọc; "Nâng lên chính thức" chỉ
// với experiment Khám phá đã kết thúc; mỗi biểu đồ có nút "Cách đọc".
import { describe, expect, it } from 'vitest'

import { listMocks } from '@/api/mocks'
import { ChartReading } from '@/components/charts/ChartReading'
import type { ExperimentStatus, RunView } from '@/contracts/api'
import { render } from '@/test-utils'

import { canPromote, filterRuns } from './results'
import { FailureCasesTab } from './tabs'

const runs = listMocks<RunView>('run_view')

describe('lọc failure case theo attack và level', () => {
  const sample = runs.find((r) => r.failure_case_ids.length > 0)
  if (!sample) throw new Error('Thiếu mock run có failure case')

  it('đúng attack và level; không lọc thì giữ nguyên', () => {
    const picked = filterRuns(runs, sample.attack_spec.name, String(sample.level))
    expect(picked.length).toBeGreaterThan(0)
    for (const run of picked) {
      expect([run.attack_spec.name, run.level]).toEqual([sample.attack_spec.name, sample.level])
    }
    expect(filterRuns(runs, null, null)).toEqual(runs)
    expect(filterRuns(runs, sample.attack_spec.name, '999')).toEqual([])
  })

  it('tab Failure case hiện bộ lọc đang áp và nút bỏ lọc', () => {
    const path = `/x?tab=cases&attack=${sample.attack_spec.name}&level=${sample.level}`
    const html = render(<FailureCasesTab runs={runs} />, path)
    expect(html).toContain('data-testid="case-filter"')
    expect(html).toContain(`${sample.attack_spec.name} · level ${sample.level}`)
    expect(html).toContain('Bỏ lọc')
    const none = render(<FailureCasesTab runs={runs} />, '/x?tab=cases&attack=khong-co')
    expect(none).toContain('Không có failure case nào khớp bộ lọc.')
  })
})

describe('nâng lên chính thức', () => {
  it.each([
    ['exploration', 'completed', true],
    ['exploration', 'cancelled', true],
    ['exploration', 'running', false],
    ['exploration', 'queued', false],
    ['official', 'completed', false],
  ] as const)('%s %s → %s', (mode, status, expected) => {
    expect(canPromote({ mode, status: status as ExperimentStatus })).toBe(expected)
  })
})

describe('Cách đọc', () => {
  it('câu kết luận một dòng, nút có aria-expanded và aria-controls trỏ tới đoạn giải thích', () => {
    const closed = render(<ChartReading sentence="Câu" reading="Giải thích" />)
    expect(closed).toContain('>Câu</p>')
    const id = /aria-controls="([^"]+)"/.exec(closed)?.[1]
    expect(closed).toContain('aria-expanded="false"')
    expect(closed).toContain(`id="${id}" hidden=""`)
    const open = render(<ChartReading sentence="Câu" reading="Giải thích" initialOpen />)
    expect(open).toContain('aria-expanded="true"')
    expect(open).not.toContain('hidden=""')
  })
})
