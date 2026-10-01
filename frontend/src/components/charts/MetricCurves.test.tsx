import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import { listMocks } from '@/api/mocks'
import type { ExperimentDetail, RunView } from '@/contracts/api'

import { axisValue, buildCurves, plotted } from './curves'
import { MetricCurves, NORMALIZED_LABEL } from './MetricCurves'

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

describe('trục hoành chuẩn hóa (Phase 6, task 32, đề xuất contract 003)', () => {
  const full = listMocks<ExperimentDetail>('experiment_detail').find(
    (e) => (e.attack_ranking ?? []).length >= 10,
  )
  if (!full) throw new Error('Thiếu mock experiment toàn catalog')
  const catalog = listMocks<RunView>('run_view').filter((r) => r.experiment_id === full.id)
  const curves = buildCurves(catalog)

  it('level / max của spec: severity 1 → 20%, level lớn nhất của dải → 100%', () => {
    const fog = curves.find((c) => c.name === 'fog')
    if (!fog) throw new Error('Thiếu mock fog')
    expect(fog.paramMax).toBe(5)
    expect(axisValue(fog, 1, true)).toBeCloseTo(20)
    expect(axisValue(fog, 5, true)).toBeCloseTo(100)
    expect(axisValue(fog, 3, false)).toBe(3)
  })

  it('mọi attack nằm trong 0–100% khi bật', () => {
    for (const curve of curves) {
      for (const point of curve.points) {
        const x = axisValue(curve, point.level, true)
        expect(x).toBeGreaterThanOrEqual(0)
        expect(x).toBeLessThanOrEqual(100)
      }
    }
  })

  it('công tắc: tắt mặc định; bật thì bảng số liệu có cột % dải', () => {
    const off = renderToStaticMarkup(<MetricCurves runs={catalog} cleanMap50={0.5} />)
    expect(off).toContain(NORMALIZED_LABEL)
    expect(off).not.toMatch(/role="switch"[^>]*checked=""/)
    expect(off).not.toContain('% dải</th>')
    const on = renderToStaticMarkup(
      <MetricCurves runs={catalog} cleanMap50={0.5} initialNormalized />,
    )
    expect(on).toMatch(/role="switch"[^>]*checked=""/)
    expect(on.split('% dải</th>')).toHaveLength(curves.length + 1)
    expect(on).toContain('20.0%') // severity 1 của corruption
  })
})
