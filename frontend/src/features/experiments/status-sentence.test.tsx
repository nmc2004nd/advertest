import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import { listMocks } from '@/api/mocks'
import type { ExperimentSummary, RunCounts } from '@/contracts/api'

import { ExperimentStatusSummary } from './ExperimentStatusSummary'
import { statusSentence } from './status-sentence'

const ZERO: RunCounts = {
  queued: 0,
  running: 0,
  completed: 0,
  failed: 0,
  skipped: 0,
  stopped_limit: 0,
  cancelled: 0,
}

describe('câu tóm tắt trạng thái (validation.md Frontend unit)', () => {
  it('đúng ví dụ trong requirements.md', () => {
    const counts = { ...ZERO, completed: 18, failed: 1, stopped_limit: 1 }
    expect(statusSentence(counts)).toBe('18/20 hoàn thành, 1 lỗi, 1 dừng do giới hạn')
  })

  it('đúng cho mọi tổ hợp run_counts trong mock', () => {
    const expected: Record<string, string> = {
      completed: '4/8 hoàn thành, 1 lỗi, 2 dừng do giới hạn, 1 bỏ qua',
      running: '0/2 hoàn thành, 1 đang chạy, 1 chưa chạy',
      queued: '0/2 hoàn thành, 2 chưa chạy',
      cancelled: '1/2 hoàn thành, 1 đã hủy',
      draft: '0/0 hoàn thành',
    }
    for (const experiment of listMocks<ExperimentSummary>('experiment_summary')) {
      const sentence = statusSentence(experiment.run_counts)
      if (experiment.status in expected) expect(sentence).toBe(expected[experiment.status])
      expect(sentence).toMatch(/^\d+\/\d+ hoàn thành/)
    }
  })

  it('component hiển thị badge và câu', () => {
    const experiment = listMocks<ExperimentSummary>('experiment_summary').find(
      (e) => e.status === 'running',
    )
    if (!experiment) throw new Error('Thiếu mock experiment running')
    const html = renderToStaticMarkup(<ExperimentStatusSummary experiment={experiment} />)
    expect(html).toContain('Đang chạy')
    expect(html).toContain('0/2 hoàn thành, 1 đang chạy, 1 chưa chạy')
  })
})
