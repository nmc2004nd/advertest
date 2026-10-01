import { Route, Routes } from 'react-router'
import { describe, expect, it } from 'vitest'

import { listMocks } from '@/api/mocks'
import type {
  AttackSpec,
  ExperimentDetail,
  ExperimentPage,
  FailureCaseView,
  Manifest,
  RunView,
} from '@/contracts/api'
import { render } from '@/test-utils'

import { EXPERIMENTS_KEY, experimentKey, failureCaseKey, failureCasesKey } from './api'
import { ExperimentDetailPage } from './ExperimentDetailPage'
import { ExperimentsPage } from './ExperimentsPage'
import { FailureCasePage } from './FailureCasePage'

const details = listMocks<ExperimentDetail>('experiment_detail')
const completed = details.find((d) => d.status === 'completed')
const running = details.find((d) => d.status === 'running')
const queued = details.find((d) => d.status === 'queued')
if (!completed || !running || !queued) throw new Error('Thiếu mock experiment_detail')
const runsOf = (id: string) => listMocks<RunView>('run_view').filter((r) => r.experiment_id === id)
const ENGINEER_ID = '0f6d2c3e-8a41-4b7d-9c5e-1a2b3c4d5e02' // mock me/engineer, chủ của mock

function detailPage(
  detail: ExperimentDetail,
  tab = '',
  me = 'engineer',
  extra: [readonly unknown[], unknown][] = [],
) {
  return render(
    <Routes>
      <Route path="/experiments/:id" element={<ExperimentDetailPage />} />
    </Routes>,
    `/experiments/${detail.id}${tab ? `?tab=${tab}` : ''}`,
    me,
    [
      [experimentKey(detail.id), detail],
      [[...experimentKey(detail.id), 'runs'], runsOf(detail.id)],
      ...extra,
    ],
  )
}

describe('/experiments', () => {
  const page = listMocks<ExperimentPage>('experiment_page').find((p) => p.items.length > 0)

  it('bảng (desktop) và thẻ (điện thoại), bộ lọc, Tải thêm, nút tạo', () => {
    const html = render(<ExperimentsPage />, '/experiments', 'engineer', [
      [
        [...EXPERIMENTS_KEY, 'list', { owner: 'me', status: '', model: '' }],
        { pages: [page], pageParams: [null] },
      ],
    ])
    expect(html).toContain('<table')
    expect(html).toContain('xl:hidden')
    expect(html).toContain('Của tôi')
    expect(html).toContain('aria-selected="true"')
    expect(html).toContain('Tải thêm')
    expect(html).toContain('href="/experiments/new"')
    for (const item of page?.items ?? []) expect(html).toContain(`href="/experiments/${item.id}"`)
  })

  it('reviewer: mặc định "Tất cả", không có nút tạo', () => {
    const html = render(<ExperimentsPage />, '/experiments', 'reviewer', [
      [
        [...EXPERIMENTS_KEY, 'list', { owner: 'all', status: '', model: '' }],
        { pages: [page], pageParams: [null] },
      ],
    ])
    expect(html).not.toContain('href="/experiments/new"')
    expect(html).toMatch(/aria-selected="true"[^>]*>Tất cả/)
  })
})

describe('/experiments/:id', () => {
  it('Tổng quan: câu trạng thái, bảng run có lý do, nút Nhân bản; không có nút Hủy khi đã xong', () => {
    const html = detailPage(completed)
    expect(html).toContain('4/8 hoàn thành')
    expect(html).toContain('Worker hết bộ nhớ ở batch 8.')
    expect(html).toContain(`href="/experiments/new?clone=${completed.id}"`)
    expect(html).not.toContain('Hủy experiment')
    expect(html.match(/role="tab"/g)).toHaveLength(5)
  })

  it('chủ sở hữu thấy nút Hủy khi đang chạy; người khác không thấy', () => {
    expect(running.owner.id).toBe(ENGINEER_ID)
    expect(detailPage(running)).toContain('Hủy experiment')
    expect(detailPage(running, '', 'reviewer')).not.toContain('Hủy experiment')
  })

  it('queued: hiện vị trí hàng đợi', () => {
    const html = detailPage(queued, '', 'reviewer')
    expect(html).toContain(`vị trí ${queued.queue_position}`)
  })

  it('Kết quả: biểu đồ và bảng số liệu', () => {
    expect(detailPage(completed, 'results')).toContain('Số liệu của fgsm')
  })

  describe('Phase 7: mục Điểm gãy', () => {
    const catalog = listMocks<AttackSpec>('attack_spec')
    const searchDone = details.find(
      (d) => d.status === 'completed' && (d.search_results ?? []).length > 0,
    )
    const searchRunning = details.find(
      (d) => d.status === 'running' && (d.search_results ?? []).length > 0,
    )
    if (!searchDone || !searchRunning) throw new Error('Thiếu mock experiment tìm ngưỡng')
    const page = (detail: ExperimentDetail) =>
      detailPage(detail, 'results', 'engineer', [
        [[...experimentKey(detail.id), 'runs'], runsOf(detail.id)],
        [['attack-specs'], catalog],
      ])

    it('thẻ mỗi attack tìm ngưỡng, so sánh và quỹ đạo (ẩn trên điện thoại), chạm thẻ để mở', () => {
      const html = page(searchDone)
      expect(html).toContain('Điểm gãy')
      const conclusions = html.match(/data-testid="ket-luan-diem-gay"/g) ?? []
      expect(conclusions).toHaveLength(
        searchDone.config.attacks.filter((a) => a.mode === 'search').length,
      )
      expect(html).toContain('Gãy tại eps ≈ 0.5/255')
      expect(html).toMatch(/class="hidden space-y-6 md:block" data-testid="diem-gay-chi-tiet"/)
      expect(html).toContain('aria-label="Mở quỹ đạo của pgd_linf"')
      expect(html).toMatch(/<button[^>]*class="absolute inset-0[^"]*md:hidden"/)
    })

    it('đường cong Phase 6 chỉ gồm attack quét lưới (không vẽ run tập con của tìm ngưỡng)', () => {
      expect(runsOf(searchDone.id).some((r) => r.scope === 'subset')).toBe(true)
      expect(page(searchDone)).not.toContain('Số liệu của pgd_linf')
    })

    it('đang chạy: dòng tiến độ tìm kiếm', () => {
      expect(page(searchRunning)).toMatch(/Điểm \d+ \/ tối đa \d+ · khoảng hiện tại/)
    })

    it('experiment chỉ quét lưới: không có mục Điểm gãy', () => {
      expect(detailPage(completed, 'results')).not.toContain('id="diem-gay"')
    })
  })

  it('Failure case: thumbnail có watermark, link tới trình xem', () => {
    const run = runsOf(completed.id).find((r) => r.failure_case_ids.length > 0)
    if (!run) throw new Error('Thiếu run có failure case')
    const cases = listMocks<FailureCaseView>('failure_case_view').filter(
      (c) => c.urls.clean === null,
    )
    const html = detailPage(completed, 'cases', 'engineer', [[failureCasesKey(run.run_id), cases]])
    expect(html).toContain('BẢN NHÁP – CHƯA DUYỆT')
    expect(html).toContain(`href="/failure-cases/${cases[0].id}?run=${run.run_id}"`)
  })

  it('Chi phí: thời gian đã dùng so với giới hạn', () => {
    expect(detailPage(completed, 'cost')).toContain('Thời gian xử lý đã dùng')
  })

  it('Tái lập: fingerprint rút gọn, git commit, tải manifest; run chưa chạy ghi rõ', () => {
    const manifest = listMocks<Manifest>('manifest')[0]
    const runs = runsOf(completed.id)
    const extra: [readonly unknown[], unknown][] = runs.map((r) => [
      ['runs', r.run_id, 'manifest'],
      manifest,
    ])
    const html = detailPage(completed, 'repro', 'engineer', extra)
    expect(html).toContain('Copy fingerprint')
    expect(html).toContain(manifest.fingerprint_inputs.git_commit)
    expect(html).toContain('Tải manifest.json')
    expect(html).toContain('Chưa chạy: chưa có fingerprint.')
  })
})

describe('/failure-cases/:id', () => {
  it('trình xem có watermark, vị trí trong run và nút chuyển case', () => {
    const views = listMocks<FailureCaseView>('failure_case_view')
    const view = views.find((v) => v.display_mode === 'normal' && v.urls.clean !== null)
    if (!view) throw new Error('Thiếu mock case')
    const list = [...new Map(views.map((v) => [v.id, v])).values()]
    const html = render(
      <Routes>
        <Route path="/failure-cases/:id" element={<FailureCasePage />} />
      </Routes>,
      `/failure-cases/${view.id}?run=${view.run_id}`,
      'engineer',
      [
        [failureCaseKey(view.id), view],
        [failureCasesKey(view.run_id), list],
      ],
    )
    expect(html).toContain(`Failure case ${view.image_id}`)
    expect(html).toContain('BẢN NHÁP – CHƯA DUYỆT')
    const position = list.findIndex((v) => v.id === view.id) + 1
    expect(html).toContain(`case ${position}/${list.length}`)
    expect(html).toContain('Case trước')
    expect(html).toContain('Case sau')
  })
})
