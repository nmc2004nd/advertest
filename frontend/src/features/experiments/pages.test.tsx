import { Route, Routes } from 'react-router'
import { describe, expect, it } from 'vitest'

import { listMocks } from '@/api/mocks'
import type {
  AttackSpec,
  ExperimentDetail,
  ExperimentInsight,
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
const insights = listMocks<ExperimentInsight>('experiment_insight')
const weakInsight = insights.find((i) => i.conclusion.code === 'weak')
const noData = insights.find((i) => i.conclusion.code === 'no_data')
if (!weakInsight || !noData) throw new Error('Thiếu mock experiment_insight')

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
      // Phase R3: tab Kết quả mở đầu bằng insight (mặc định có điểm yếu).
      [[...experimentKey(detail.id), 'insight'], { ...weakInsight, experiment_id: detail.id }],
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

  describe('Phase R3: insight đầu tab Kết quả', () => {
    const exploration = { ...completed, mode: 'exploration' as const }
    const official = { ...completed, mode: 'official' as const }

    it('câu kết luận, điểm yếu có data-level, ma trận 4 ô mỗi hàng, chú thích thang màu', () => {
      const html = detailPage(exploration, 'results')
      expect(html).toContain('data-testid="insight-conclusion"')
      expect(html).toContain(weakInsight.conclusion.text)
      const weak = [
        ...html.matchAll(/data-testid="weakness" data-attack="([^"]+)" data-level="([^"]+)"/g),
      ]
      expect(weak.map((m) => [m[1], Number(m[2])])).toEqual(
        weakInsight.weaknesses.map((w) => [w.attack_name, w.level]),
      )
      const cells = html.match(/data-testid="matrix-cell"/g) ?? []
      expect(cells).toHaveLength(weakInsight.matrix.length * 4)
      expect(html).toContain('Chưa chạy')
      expect(html).toContain('data-testid="matrix-legend"')
      expect(html).toContain('0–25% dải')
      // Câu kết luận và nút "Cách đọc" cho ma trận và mọi biểu đồ có sẵn.
      expect((html.match(/>Cách đọc</g) ?? []).length).toBeGreaterThanOrEqual(3)
      expect(html).toContain('data-term="map"')
    })

    it('ô ma trận tô theo thang màu, ô ≥ 30% có viền', () => {
      const html = detailPage(exploration, 'results')
      const tones = [
        ...html.matchAll(
          /data-testid="matrix-cell" data-band="\d" data-tone="(\w+)" class="([^"]*)"/g,
        ),
      ]
      expect(tones.map((m) => m[1])).toEqual(
        weakInsight.matrix.flatMap((row) =>
          row.cells.map((c) => {
            const d = c.max_relative_drop
            if (d === null) return 'empty'
            return d < 0.1 ? 'none' : d < 0.3 ? 'low' : d < 0.5 ? 'mid' : 'high'
          }),
        ),
      )
      for (const [, tone, cls] of tones) {
        expect(cls.includes('border-fail')).toBe(tone === 'mid' || tone === 'high')
      }
    })

    it('kết quả một phần có nhãn', () => {
      const html = detailPage(exploration, 'results', 'engineer', [
        [[...experimentKey(exploration.id), 'insight'], { ...weakInsight, partial: true }],
      ])
      expect(html).toContain('Kết quả một phần')
    })

    it('no_data: trạng thái trống, không có ma trận, không có nút nâng lên', () => {
      const html = detailPage(exploration, 'results', 'engineer', [
        [[...experimentKey(exploration.id), 'insight'], noData],
      ])
      expect(html).toContain('data-testid="empty-state"')
      expect(html).toContain('Chưa có run nào có kết quả')
      expect(html).not.toContain('robustness-matrix')
      expect(html).not.toContain('Nâng lên chính thức')
    })

    it('"Nâng lên chính thức" chỉ với experiment Khám phá đã kết thúc và người có quyền tạo', () => {
      expect(detailPage(exploration, 'results')).toContain('Nâng lên chính thức</button>')
      expect(detailPage({ ...exploration, status: 'cancelled' }, 'results')).toContain(
        'Nâng lên chính thức</button>',
      )
      expect(detailPage(official, 'results')).not.toContain('Nâng lên chính thức')
      expect(detailPage({ ...exploration, status: 'running' }, 'results')).not.toContain(
        'Nâng lên chính thức',
      )
      expect(detailPage(exploration, 'results', 'reviewer')).not.toContain('Nâng lên chính thức')
    })
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

describe('/experiments/:id Phase R3 (validation.md Group 4)', () => {
  const byStatus = (mode: string, status: string) => {
    const found = details.find((d) => d.mode === mode && d.status === status && !d.promoted_from)
    if (!found) throw new Error(`Thiếu mock ${mode} ${status}`)
    return found
  }
  const tabNames = (html: string) =>
    [...html.matchAll(/role="tab"[^>]*>([^<]+)</g)].map((m) => m[1])
  const selectedTab = (html: string) =>
    /role="tab" aria-selected="true"[^>]*>([^<]+)</.exec(html)?.[1]

  it('đúng 5 tab theo thứ tự; Review và Report luôn hiện', () => {
    expect(tabNames(detailPage(completed))).toEqual([
      'Tổng quan',
      'Kết quả',
      'Failure case',
      'Review',
      'Report',
    ])
  })

  it.each([
    ['cost', 'Chi phí', 'Thời gian xử lý đã dùng'],
    ['repro', 'Tái lập', 'Chưa chạy: chưa có fingerprint.'],
  ])('?tab=%s cũ mở Tổng quan, section "%s" mở sẵn', (tab, heading, content) => {
    const html = detailPage(completed, tab)
    expect(selectedTab(html)).toBe('Tổng quan')
    expect(html).toMatch(new RegExp(`aria-expanded="true"[^>]*>${heading}<`))
    expect(html).toContain(content)
  })

  it('Tổng quan mặc định: section Chi phí và Tái lập thu gọn, không render nội dung', () => {
    const html = detailPage(completed)
    expect(html).toMatch(/aria-expanded="false"[^>]*>Chi phí</)
    expect(html).toMatch(/aria-expanded="false"[^>]*>Tái lập</)
    expect(html).not.toContain('Thời gian xử lý đã dùng')
  })

  it('nhãn mode và thanh vòng đời: Khám phá 3 bước, Chính thức 6 bước', () => {
    const exploration = detailPage(completed)
    expect(exploration).toMatch(/data-testid="experiment-mode"[^>]*>.*Khám phá/)
    expect(exploration.match(/data-testid="lifecycle-step"/g)).toHaveLength(3)
    const official = detailPage(byStatus('official', 'completed'))
    expect(official).toMatch(/data-testid="experiment-mode"[^>]*>.*Chính thức/)
    expect(official.match(/data-testid="lifecycle-step"/g)).toHaveLength(6)
    expect(official).toContain('data-step="analyze" data-state="current"')
  })

  it('promoted_from: link "Nâng từ <tên nguồn>"', () => {
    const promoted = details.find((d) => d.promoted_from)
    if (!promoted?.promoted_from) throw new Error('Thiếu mock promoted_official')
    const source = { ...completed, id: promoted.promoted_from, name: 'kham-pha-fgsm' }
    const html = detailPage(promoted, '', 'engineer', [[experimentKey(source.id), source]])
    expect(html).toContain(`href="/experiments/${source.id}"`)
    expect(html).toContain('Nâng từ kham-pha-fgsm')
    expect(detailPage(completed)).not.toContain('Nâng từ')
  })

  it('tab Review và Report của experiment Khám phá: trạng thái trống nói điều gì còn thiếu', () => {
    const review = detailPage(completed, 'review')
    expect(review).toContain('data-testid="empty-state"')
    expect(review).toContain('Experiment Khám phá không gửi duyệt được')
    const report = detailPage(completed, 'report')
    expect(report).toContain('data-testid="empty-state"')
    expect(report).toContain('Experiment Khám phá không có report')
  })

  it('tab Report: report đã có thì hiện kết luận và link tới report', () => {
    const approved = details.find((d) => d.report?.status === 'ready')
    if (!approved?.report) throw new Error('Thiếu mock report ready')
    const html = detailPage(approved, 'report', 'reviewer')
    expect(html).not.toContain('data-testid="empty-state"')
    expect(html).toContain(`href="/reports/${approved.report.id}"`)
  })

  it('tab Report khi bị yêu cầu sửa: trạng thái trống kèm "Nhân bản để sửa"', () => {
    const changes = byStatus('official', 'changes_requested')
    const html = detailPage(changes, 'report')
    expect(html).toContain('Reviewer yêu cầu sửa')
    expect(html.match(/Nhân bản để sửa/g)?.length).toBeGreaterThanOrEqual(2)
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
