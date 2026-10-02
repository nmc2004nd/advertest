/** Phase 8 (plan task 27-29, 31): hàng đợi, trang review, khung quyết định, verdict và phím tắt. */
import { Route, Routes } from 'react-router'
import { describe, expect, it } from 'vitest'

import { listMocks, mockMe } from '@/api/mocks'
import type {
  CaseVerdictView,
  ExperimentDetail,
  FailureCaseView,
  ReviewQueueItem,
} from '@/contracts/api'
import { experimentKey, failureCaseKey } from '@/features/experiments/api'
import { HomePage } from '@/pages/HomePage'
import { expectLabelledControls, render } from '@/test-utils'

import { REVIEWS_KEY, verdictsKey } from './api'
import { approveBlockers, decisionBody, EMPTY_DECISION, otherBlockers } from './decision'
import { ReviewCasePage, ShortcutTable, VerdictForm } from './ReviewCasePage'
import { DecisionPanel, ReviewPage } from './ReviewPage'
import { ReviewsPage } from './ReviewsPage'
import {
  applyShortcut,
  isTextField,
  type KeyLike,
  neighbours,
  shortcutOf,
  type VerdictDraft,
  verdictBody,
} from './verdict'

const details = Object.fromEntries(
  Object.entries(
    import.meta.glob<ExperimentDetail>('../../../../contracts/mocks/experiment_detail/*.json', {
      eager: true,
      import: 'default',
    }),
  ).map(([path, data]) => [path.split('/').pop()?.replace('.json', '') ?? path, data]),
)
const mock = (name: string): ExperimentDetail => {
  const found = details[name]
  if (!found) throw new Error(`Thiếu mock ${name}`)
  return found
}
const reviewOf = (detail: ExperimentDetail) => {
  if (!detail.review) throw new Error(`Mock ${detail.name} không có review`)
  return detail.review
}
const queue = listMocks<ReviewQueueItem>('review_queue_item')
const verdicts = listMocks<CaseVerdictView>('case_verdict_view')
const cases = listMocks<FailureCaseView>('failure_case_view')

const partial = mock('review_in_review_partial')
const ready = mock('review_in_review_ready')
const filled = {
  conclusion: 'Model giữ được mAP dưới fog nhẹ.',
  mitigation: 'Bổ sung dữ liệu fog.',
  modelVerdict: 'conditional' as const,
  inconclusiveJustification: 'Slice nhỏ, ghi nhận.',
}

/** HTML của một nút theo nhãn (SSR: `disabled=""` nằm trong thẻ mở). */
function button(html: string, label: string): string {
  const match = [...html.matchAll(/<button[^>]*>(.*?)<\/button>/g)].find((m) =>
    m[1].replace(/<[^>]+>/g, '').includes(label),
  )
  if (!match) throw new Error(`Không thấy nút ${label}`)
  return match[0]
}
const isDisabled = (html: string, label: string) =>
  /^<button[^>]*\sdisabled=""/.test(button(html, label))

describe('hàng đợi review', () => {
  it('ba nhóm, sắp xếp, bảng desktop và thẻ điện thoại kèm tiến độ case', () => {
    const waiting = queue.filter((i) => i.experiment.status === 'submitted_for_review')
    const html = render(<ReviewsPage />, '/reviews', 'reviewer', [
      [[...REVIEWS_KEY, 'waiting', 'submitted_at'], waiting],
    ])
    for (const text of ['Chờ nhận', 'Tôi đang review', 'Đã quyết định', 'Mức sụt lớn nhất']) {
      expect(html).toContain(text)
    }
    expect(html).toContain('aria-selected="true"')
    expect(html).toContain('<table')
    expect(html).toContain('xl:hidden')
    expect(html).toContain(waiting[0].experiment.name)
    expect(html).toContain(
      `${waiting[0].required_cases_reviewed}/${waiting[0].required_cases_total} case đã review`,
    )
    expectLabelledControls(html, 1)
  })

  it('nhóm "Đã quyết định" hiện quyết định', () => {
    const decided = queue.filter((i) => i.decision)
    const html = render(<ReviewsPage />, '/reviews?status=decided&sort=max_drop', 'reviewer', [
      [[...REVIEWS_KEY, 'decided', 'max_drop'], decided],
    ])
    expect(html).toContain('Chấp nhận')
    expect(html).toContain('Yêu cầu sửa')
  })
})

function reviewPage(detail: ExperimentDetail, me = 'reviewer') {
  return render(
    <Routes>
      <Route path="/reviews/:id" element={<ReviewPage />} />
    </Routes>,
    `/reviews/${detail.id}`,
    me,
    [
      [experimentKey(detail.id), detail],
      [[...experimentKey(detail.id), 'runs'], []],
    ],
  )
}

describe('trang review', () => {
  it('chờ nhận: nút "Nhận review", chưa có khung quyết định', () => {
    const html = reviewPage(mock('review_submitted_waiting'))
    expect(html).toContain('Nhận review')
    expect(html).not.toContain('khung-quyet-dinh')
  })

  it('người tạo experiment không thấy nút nhận và được báo lý do', () => {
    const waiting = mock('review_submitted_waiting')
    const me = mockMe('engineer_reviewer')
    const own = { ...waiting, owner: { ...waiting.owner, id: me.id } }
    const html = reviewPage(own, 'engineer_reviewer')
    expect(html).not.toContain('Nhận review')
    expect(html).toContain('không được review experiment do mình tạo')
    expect(reviewPage(waiting, 'engineer_reviewer')).toContain('Nhận review')
  })

  it('đang review: checklist ✓/✗ kèm lý do, case bắt buộc theo attack có tiến độ, khung quyết định', () => {
    const html = reviewPage(partial)
    const review = reviewOf(partial)
    expect(html).toContain('danh-sach-kiem-tra')
    expect(html).toContain('Chưa đạt: ')
    for (const item of review.checklist) expect(html).toContain(item.detail)
    const done = review.required_cases.filter((c) => c.current_verdict).length
    expect(html).toContain(`${done}/${review.required_cases.length} đã review`)
    expect(html).toContain(
      `/reviews/${partial.id}/cases/${review.required_cases[0].failure_case_id}`,
    )
    expect(html).toContain('Trả lại')
    expect(html).toContain('khung-quyet-dinh')
    expect(html).toContain('Chưa kết luận')
  })
})

describe('khung quyết định', () => {
  it('Nút Chấp nhận bị khóa khi checklist còn mục chưa thỏa, và hiển thị lý do', () => {
    const review = reviewOf(partial)
    const html = render(<DecisionPanel experiment={partial} review={review} initial={filled} />)
    expect(isDisabled(html, 'Chấp nhận')).toBe(true)
    expect(html).toContain('ly-do-khoa')
    const unmet = review.checklist.filter((c) => !c.satisfied)
    expect(unmet.length).toBeGreaterThan(0)
    for (const item of unmet) expect(html).toContain(item.detail)
    // Yêu cầu sửa và từ chối không cần checklist.
    expect(isDisabled(html, 'Yêu cầu sửa')).toBe(false)
    expect(isDisabled(html, 'Từ chối')).toBe(false)
  })

  it('checklist đủ nhưng thiếu ô bắt buộc: vẫn khóa, nêu ô thiếu', () => {
    const review = reviewOf(ready)
    const html = render(<DecisionPanel experiment={ready} review={review} />)
    expect(isDisabled(html, 'Chấp nhận')).toBe(true)
    expect(html).toContain('Chưa có kết luận')
    expect(html).toContain('Chưa chọn kết luận về model')
    // Có tiêu chí chưa kết luận: ô giải trình hiện ra.
    expect(html).toContain('Giải trình tiêu chí chưa kết luận')
    expectLabelledControls(html, 4)
  })

  it('checklist đủ và đủ ô: Chấp nhận mở khóa', () => {
    const review = reviewOf(ready)
    const html = render(<DecisionPanel experiment={ready} review={review} initial={filled} />)
    expect(isDisabled(html, 'Chấp nhận')).toBe(false)
    expect(html).not.toContain('ly-do-khoa')
    expect(approveBlockers(review, filled)).toEqual([])
  })

  it('giải trình chỉ bắt buộc khi có tiêu chí chưa kết luận; body gửi đúng trường', () => {
    const review = reviewOf(ready)
    const noJustification = { ...filled, inconclusiveJustification: '' }
    expect(approveBlockers(review, noJustification)).toContain(
      'Có tiêu chí chưa kết luận: cần giải trình',
    )
    const allPass = {
      ...review,
      criteria_results: review.criteria_results.map((c) => ({ ...c, status: 'pass' as const })),
    }
    expect(approveBlockers(allPass, noJustification)).toEqual([])
    expect(otherBlockers(EMPTY_DECISION)).toHaveLength(1)
    expect(decisionBody('reject', { ...EMPTY_DECISION, conclusion: ' Sai slice ' })).toEqual({
      decision: 'reject',
      conclusion: 'Sai slice',
      mitigation: null,
      model_verdict: null,
      inconclusive_justification: null,
    })
  })
})

const key = (k: string, extra: Partial<KeyLike> = {}): KeyLike => ({
  key: k,
  ctrlKey: false,
  metaKey: false,
  altKey: false,
  inField: false,
  ...extra,
})

describe('phím tắt verdict', () => {
  it('Phím tắt verdict gửi đúng giá trị', () => {
    let draft: VerdictDraft = { severity: null, kind: null, mitigation: '' }
    for (const k of ['2', 'a']) {
      const action = shortcutOf(key(k))
      if (!action) throw new Error(k)
      draft = applyShortcut(draft, action)
    }
    expect(shortcutOf(key('Enter', { ctrlKey: true }))).toEqual({ type: 'save' })
    expect(verdictBody(draft)).toEqual({
      body: { severity: 'major', kind: 'acceptable', mitigation: null },
    })
    const all = ['1', '2', '3', '4', 'S', 'A', 'N'].map((k) => shortcutOf(key(k)))
    expect(all).toEqual([
      { type: 'severity', value: 'critical' },
      { type: 'severity', value: 'major' },
      { type: 'severity', value: 'minor' },
      { type: 'severity', value: 'acceptable' },
      { type: 'kind', value: 'safety_relevant' },
      { type: 'kind', value: 'acceptable' },
      { type: 'kind', value: 'annotation_issue' },
    ])
    expect(shortcutOf(key('j'))).toEqual({ type: 'next' })
    expect(shortcutOf(key('K'))).toEqual({ type: 'prev' })
  })

  it('? mở bảng phím tắt; phím chữ trong ô nhập không phải phím tắt, Ctrl+Enter vẫn lưu', () => {
    expect(shortcutOf(key('?'))).toEqual({ type: 'help' })
    const table = render(<ShortcutTable />)
    for (const k of ['J / K', '1 – 4', 'S / A / N', 'Ctrl + Enter', '?']) {
      expect(table).toContain(k)
    }
    expect(shortcutOf(key('1', { inField: true }))).toBeNull()
    expect(shortcutOf(key('?', { inField: true }))).toBeNull()
    expect(shortcutOf(key('Enter', { inField: true, metaKey: true }))).toEqual({ type: 'save' })
    expect(shortcutOf(key('s', { ctrlKey: true }))).toBeNull()
    expect(isTextField({ tagName: 'TEXTAREA' } as unknown as EventTarget)).toBe(true)
    expect(isTextField({ tagName: 'BUTTON' } as unknown as EventTarget)).toBe(false)
  })

  it('ảnh hưởng an toàn cần biện pháp khắc phục', () => {
    expect(verdictBody({ severity: 'critical', kind: 'safety_relevant', mitigation: ' ' })).toEqual(
      {
        error: 'Verdict ảnh hưởng an toàn cần biện pháp khắc phục',
      },
    )
  })

  it('J/K đi theo thứ tự case bắt buộc', () => {
    const ids = reviewOf(partial).required_cases.map((c) => c.failure_case_id)
    expect(neighbours(partial, ids[0])).toMatchObject({ index: 0, prev: undefined, next: ids[1] })
    expect(neighbours(partial, 'khac').index).toBe(-1)
  })
})

describe('trang verdict của case', () => {
  const caseId = reviewOf(partial).required_cases[0].failure_case_id
  const view = cases.find((c) => c.id === caseId)
  const history = verdicts.filter((v) => v.failure_case_id === caseId)

  it('trình xem, form verdict có nhãn, lịch sử mới nhất trước, nút mở bottom sheet', () => {
    if (!view) throw new Error('thiếu mock case')
    const html = render(
      <Routes>
        <Route path="/reviews/:id/cases/:caseId" element={<ReviewCasePage />} />
      </Routes>,
      `/reviews/${partial.id}/cases/${caseId}`,
      'reviewer',
      [
        [experimentKey(partial.id), partial],
        [failureCaseKey(caseId), view],
        [verdictsKey(caseId), [...history].sort((a, b) => b.version - a.version)],
      ],
    )
    expect(html).toContain('Case bắt buộc 1/')
    expect(html).toContain('lich-su-verdict')
    expect(html.indexOf(`v${history.length}:`)).toBeLessThan(html.indexOf('v1:'))
    expect(html).toContain('Ghi verdict')
    expect(html).toContain('role="radiogroup"')
    expect(html).toContain('Phím tắt (?)')
  })

  it('form: nút lớn, khóa khi chưa đủ; người không nhận review không ghi được', () => {
    const empty = { severity: null, kind: null, mitigation: '' }
    const props = { onChange: () => undefined, onSave: () => undefined, saving: false, error: null }
    const html = render(<VerdictForm {...props} draft={empty} disabled={false} idPrefix="v" />)
    expect(html).toContain('min-h-12')
    expect(isDisabled(html, 'Lưu verdict')).toBe(true)
    expect(html).toContain('Chọn mức nghiêm trọng')
    expectLabelledControls(html, 1)
    const ok = render(
      <VerdictForm
        {...props}
        draft={{ severity: 'minor', kind: 'annotation_issue', mitigation: '' }}
        disabled={false}
        idPrefix="v"
      />,
    )
    expect(isDisabled(ok, 'Lưu verdict')).toBe(false)
    expect(ok).toContain('aria-checked="true"')
  })
})

describe('trang chủ reviewer', () => {
  it('số experiment chờ nhận và danh sách tôi đang review', () => {
    const waiting = queue.filter((i) => i.experiment.status === 'submitted_for_review')
    const mine = queue.filter((i) => i.experiment.status === 'in_review')
    const html = render(<HomePage />, '/home', 'reviewer', [
      [[...REVIEWS_KEY, 'waiting', 'submitted_at'], waiting],
      [[...REVIEWS_KEY, 'mine', 'submitted_at'], mine],
    ])
    expect(html).toContain('so-cho-nhan')
    expect(html).toContain(`>${waiting.length}</span>`)
    expect(html).toContain(mine[0].experiment.name)
    expect(html).toContain(`/reviews/${mine[0].experiment.id}`)
  })
})
