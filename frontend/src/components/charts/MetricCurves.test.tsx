import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import { listMocks } from '@/api/mocks'
import type { ExperimentDetail, RunView } from '@/contracts/api'

import { buildCurves, plotted } from './curves'
import { MetricCurves } from './MetricCurves'

const detail = listMocks<ExperimentDetail>('experiment_detail').find(
  (e) => e.status === 'completed',
)
if (!detail) throw new Error('Thiếu mock experiment completed')
const runs = listMocks<RunView>('run_view').filter((r) => r.experiment_id === detail.id)

describe('dữ liệu đường cong', () => {
  it('gom theo attack, điểm sắp theo level, giữ cả run không có metric', () => {
    const curves = buildCurves(runs)
    expect(curves.map((c) => c.name)).toEqual(['fgsm', 'pgd_linf', 'pgd_l2'])
    expect(curves.flatMap((c) => c.points)).toHaveLength(runs.length)
    for (const curve of curves) {
      const levels = curve.points.map((p) => p.level)
      expect(levels).toEqual([...levels].sort((a, b) => a - b))
    }
  })

  it('đánh dấu run partial; chỉ vẽ run có metric', () => {
    const pgd = buildCurves(runs).find((c) => c.name === 'pgd_linf')
    if (!pgd) throw new Error('Thiếu pgd_linf')
    expect(pgd.points.filter((p) => p.partial).map((p) => p.level)).toEqual([16])
    // pgd_linf eps 8 lỗi (không metric): có trong bảng, không vẽ.
    expect(pgd.points.map((p) => p.level)).toEqual([2, 4, 8, 16])
    expect(plotted(pgd, 'map50').map((p) => p.level)).toEqual([2, 4, 16])
  })
})

describe('MetricCurves (validation.md: biểu đồ đánh dấu run partial, bảng số liệu đủ giá trị)', () => {
  const html = renderToStaticMarkup(<MetricCurves runs={runs} cleanMap50={0.512} />)

  it('mỗi run một dòng trong bảng, có giá trị metric', () => {
    expect(html.match(/<tr class="border-t"/g)).toHaveLength(runs.length)
    for (const run of runs) {
      if (run.metrics) expect(html).toContain(run.metrics.attacked.map50.toFixed(3))
    }
    expect(html).toContain('<caption class="sr-only">Số liệu của fgsm</caption>')
  })

  it('run partial được đánh dấu trong bảng và có chú thích', () => {
    expect(html.match(/data-partial="true"/g)).toHaveLength(1)
    expect(html).toContain('một phần ảnh')
    expect(html).toContain('Run dừng giữa chừng')
  })

  it('điện thoại có tab chuyển biểu đồ', () => {
    expect(html).toContain('role="tablist"')
    expect(html).toContain('aria-selected="true"')
  })

  it('attack không có run nào có metric: báo thay vì vẽ khung trống', () => {
    expect(html).toContain('Chưa có run nào có metric để vẽ.')
  })

  it('không có run thì báo rõ', () => {
    expect(renderToStaticMarkup(<MetricCurves runs={[]} cleanMap50={null} />)).toContain(
      'Chưa có run nào.',
    )
  })
})
