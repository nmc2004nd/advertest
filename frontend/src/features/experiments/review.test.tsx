/** Phase 8 (plan task 25, 26): gửi duyệt, dải "Đã khóa", tab Review, "Nhân bản để sửa". */
import { Route, Routes } from 'react-router'
import { describe, expect, it } from 'vitest'

import { listMocks } from '@/api/mocks'
import type { ExperimentDetail, ReviewComment, RunView } from '@/contracts/api'
import { expectLabelledControls, render } from '@/test-utils'

import { experimentKey } from './api'
import { ExperimentDetailPage } from './ExperimentDetailPage'
import { commentsKey } from './review-api'
import { canSubmit, lockedBannerText } from './review-labels'
import { ReviewTab } from './ReviewTab'
import { SubmitFields } from './SubmitDialog'

const byName = Object.fromEntries(
  Object.entries(
    import.meta.glob<ExperimentDetail>('../../../../contracts/mocks/experiment_detail/*.json', {
      eager: true,
      import: 'default',
    }),
  ).map(([path, data]) => [path.split('/').pop()?.replace('.json', '') ?? path, data]),
)
const mock = (name: string): ExperimentDetail => {
  const found = byName[name]
  if (!found) throw new Error(`Thiếu mock ${name}`)
  return found
}
const runs = listMocks<RunView>('run_view')
const comments = listMocks<ReviewComment>('review_comment')

function page(detail: ExperimentDetail, tab = '', me = 'engineer') {
  return render(
    <Routes>
      <Route path="/experiments/:id" element={<ExperimentDetailPage />} />
    </Routes>,
    `/experiments/${detail.id}${tab ? `?tab=${tab}` : ''}`,
    me,
    [
      [experimentKey(detail.id), detail],
      [[...experimentKey(detail.id), 'runs'], runs],
      [commentsKey(detail.id), comments.filter((c) => c.experiment_id === detail.id)],
    ],
  )
}

describe('gửi duyệt', () => {
  const ready = mock('review_completed_ready_to_submit')
  const blocked = mock('review_completed_dirty_blocked')

  it('chủ sở hữu thấy nút "Gửi duyệt" khi completed và protocol không phải dev', () => {
    expect(page(ready)).toContain('Gửi duyệt')
    expect(page(ready, '', 'reviewer')).not.toContain('Gửi duyệt')
    // Mock Phase 5 gắn dev-open: không có nút.
    expect(page(mock('completed'))).not.toContain('Gửi duyệt')
  })

  it('canSubmit theo submit_check', () => {
    expect(canSubmit(ready)).toBe(true)
    expect(canSubmit(blocked)).toBe(false)
    expect(canSubmit(mock('completed'))).toBe(false)
  })

  it('hộp gửi duyệt: điều kiện ✓/✗, ô giải trình cho từng run, ghi chú; lỗi 422 tại đúng ô', () => {
    const needed = blocked.runs_requiring_explanation ?? []
    expect(needed.length).toBeGreaterThan(0)
    const html = render(
      <SubmitFields
        experiment={blocked}
        runs={runs}
        note=""
        onNote={() => undefined}
        explanations={{}}
        onExplanation={() => undefined}
        fieldErrors={{ [`run_explanations.${needed[0]}`]: 'Run bắt buộc này cần lời giải trình' }}
        error="Lỗi"
      />,
    )
    expect(html).toContain('Chưa đạt: ')
    expect(html).toContain('Không có run chạy từ code chưa commit')
    expect(html).toContain(`(0/${needed.length})`)
    expect(html).toContain('Run bắt buộc này cần lời giải trình')
    expect(html).toContain('pgd_linf')
    // Mỗi run một ô giải trình, cộng ô ghi chú; đều có nhãn và font 16px.
    expectLabelledControls(html, needed.length + 1)
  })
})

describe('sau khi gửi', () => {
  it('dải "Đã khóa – đang chờ duyệt" và tab Review; không có nút Gửi duyệt', () => {
    const waiting = mock('review_submitted_waiting')
    const html = page(waiting)
    expect(html).toContain('data-testid="dai-khoa"')
    expect(html).toContain('Đã khóa – đang chờ duyệt')
    expect(html).toContain('>Review<')
    expect(html).not.toContain('Gửi duyệt<')
  })

  it('tab Review: người nhận, giải trình, bình luận, ô bình luận khi đang review', () => {
    const inReview = mock('review_in_review_partial')
    const html = page(inReview, 'review')
    expect(html).toContain('Đỗ Thu Hà')
    expect(html).toContain('Worker hết bộ nhớ')
    expect(html).toContain('Tiêu chí PGD eps 8 chưa kết luận được')
    expect(html).toContain('Thêm bình luận')
  })

  it('đã quyết định: hiện quyết định, không còn ô bình luận', () => {
    const html = render(
      <ReviewTab experiment={mock('review_approved_report_ready')} runs={runs} />,
      '/',
      'engineer',
    )
    expect(html).toContain('Quyết định: Chấp nhận')
    expect(html).toContain('Model không đạt tiêu chí')
    expect(html).not.toContain('Thêm bình luận')
  })

  it('yêu cầu sửa: nút "Nhân bản để sửa" mở wizard với cấu hình cũ', () => {
    const changes = mock('review_changes_requested')
    const html = page(changes)
    expect(html).toContain('Nhân bản để sửa')
    expect(html).toContain(`href="/experiments/new?clone=${changes.id}"`)
    expect(lockedBannerText('changes_requested')).toContain('nhân bản')
  })

  it('experiment chưa gửi duyệt không có tab Review (kể cả khi URL chỉ định)', () => {
    const html = page(mock('completed'), 'review')
    expect(html).not.toContain('>Review<')
    expect(lockedBannerText('completed')).toBeNull()
  })
})
