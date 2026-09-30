import { describe, expect, it } from 'vitest'

import { listMocks } from '@/api/mocks'
import type { ExperimentSummary } from '@/contracts/api'

import { splitMine } from './home'

describe('khối engineer trên /home', () => {
  const all = listMocks<ExperimentSummary>('experiment_summary')

  it('đang chạy hoặc chờ; tối đa 5 cái kết thúc gần nhất, mới nhất trước', () => {
    const { active, finished } = splitMine(all)
    expect(new Set(active.map((e) => e.status))).toEqual(new Set(['queued', 'running']))
    expect(finished.length).toBeLessThanOrEqual(5)
    const times = finished.map((e) => e.finished_at ?? '')
    expect(times).toEqual([...times].sort().reverse())
    expect(finished.every((e) => e.finished_at !== null)).toBe(true)
  })
})
