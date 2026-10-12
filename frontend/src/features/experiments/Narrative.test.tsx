import { describe, expect, it } from 'vitest'

import { listMocks } from '@/api/mocks'
import type { ExperimentDetail, ExperimentNarrative, NarrativeState } from '@/contracts/api'
import { NARRATIVE } from '@/copy/narrative'
import { render } from '@/test-utils'

import { experimentKey } from './api'
import { NarrativeSection } from './Narrative'

const completed = listMocks<ExperimentDetail>('experiment_detail').find(
  (d) => d.status === 'completed',
)
const narrative = listMocks<ExperimentNarrative>('experiment_narrative')[0]
if (!completed || !narrative) throw new Error('Thiếu mock experiment_detail / experiment_narrative')
const experiment: ExperimentDetail = completed

function section(state: NarrativeState | undefined) {
  const data: [readonly unknown[], unknown][] = state
    ? [[[...experimentKey(experiment.id), 'narrative'], state]]
    : []
  return render(<NarrativeSection experiment={experiment} />, '/', 'engineer', data)
}

const base: NarrativeState = { enabled: true, narrative: null, stale: false, can_generate: true }

describe('Nhận xét chi tiết (LLM)', () => {
  it('ẩn khi server chưa cấu hình LLM hoặc chưa đọc được trạng thái', () => {
    expect(section({ ...base, enabled: false })).toBe('')
    expect(section(undefined)).toBe('')
  })

  it('chưa có nhận xét: giới thiệu, nhãn AI viết, nút Tạo nhận xét', () => {
    const html = section(base)
    expect(html).toContain(NARRATIVE.title)
    expect(html).toContain(NARRATIVE.badge)
    expect(html).toContain(NARRATIVE.disclaimer)
    expect(html).toContain(NARRATIVE.intro)
    expect(html).toContain(`${NARRATIVE.create}</button>`)
    expect(html).not.toContain('data-testid="narrative"')
  })

  it('experiment chưa xong: không có nút, nói khi nào tạo được', () => {
    const html = section({ ...base, can_generate: false })
    expect(html).toContain(NARRATIVE.waiting)
    expect(html).not.toContain('<button')
  })

  it('đã có nhận xét: tóm tắt, phân tích, gợi ý, model; không có nút tạo', () => {
    const html = section({ ...base, narrative })
    expect(html).toContain('data-testid="narrative"')
    expect(html).toContain(narrative.summary)
    for (const finding of narrative.findings) expect(html).toContain(finding.title)
    for (const step of narrative.next_steps) expect(html).toContain(step)
    expect(html).toContain(NARRATIVE.findings)
    expect(html).toContain(NARRATIVE.nextSteps)
    expect(html).toContain(narrative.llm_model)
    expect(html).not.toContain('<button')
    expect(html).not.toContain(NARRATIVE.stale)
  })

  it('số liệu đã đổi: vẫn hiện bản cũ, báo cũ và có nút tạo lại', () => {
    const html = section({ ...base, narrative, stale: true })
    expect(html).toContain(narrative.summary)
    expect(html).toContain(NARRATIVE.stale)
    expect(html).toContain(`${NARRATIVE.recreate}</button>`)
  })

  it('bản viết từ kết quả một phần có nhãn riêng', () => {
    const html = section({ ...base, narrative: { ...narrative, partial: true } })
    expect(html).toContain(NARRATIVE.partial)
  })
})
