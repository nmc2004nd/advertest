import { describe, expect, it } from 'vitest'

import { listMocks } from '@/api/mocks'
import type { AttackSpec, SearchResult } from '@/contracts/api'
import { render } from '@/test-utils'

import { BreakpointCard } from './BreakpointCard'
import { BreakpointComparison } from './BreakpointComparison'
import {
  BELOW_MIN_LABEL,
  conclusion,
  NEAR_THRESHOLD,
  NON_MONOTONIC,
  NOT_REACHED_LABEL,
  progressText,
  type SearchAttack,
  specInfoMap,
} from './breakpoints'
import { SearchTrajectory, TRAJECTORY_LEGEND } from './SearchTrajectory'

const results = listMocks<SearchResult>('search_result')
const specs = specInfoMap([], listMocks<AttackSpec>('attack_spec'))

function attack(r: SearchResult | null): SearchAttack {
  const spec = (r && specs.get(r.attack_spec_id)) ?? {
    name: 'fgsm',
    paramName: 'eps',
    paramUnit: '1/255',
    paramMax: 32,
  }
  return {
    attackSpecId: r?.attack_spec_id ?? 'cho',
    spec,
    config: {
      threshold_kind: r?.threshold_kind ?? 'relative_drop',
      threshold: r?.threshold ?? 0.2,
      lo: r?.status === 'below_min' ? r.bracket[0] : 0,
      hi: spec.paramMax,
      tol: spec.paramMax / 256,
      coarse_n: 4,
      subset_size: 100,
      class_filter: r?.class_filter ?? null,
      bootstrap_samples: 200,
    },
    result: r,
  }
}
const byStatus = (status: SearchResult['status']) => {
  const r = results.find((x) => x.status === status)
  if (!r) throw new Error(`Thiếu mock ${String(status)}`)
  return r
}
/** Văn bản như react-dom/server in ra (thoát `&`, `<`, `>`). */
const escape = (text: string) =>
  text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')

describe('thẻ tóm tắt điểm gãy (task 27)', () => {
  it.each(results.map((r) => [r.status ?? 'đang chạy', r] as const))(
    '%s: badge trạng thái và câu kết luận',
    (_, r) => {
      const html = render(<BreakpointCard attack={attack(r)} />)
      expect(html).toContain(escape(conclusion(attack(r))))
      if (r.status) expect(html).toContain(`data-status="${r.status}"`)
      expect(html).toContain('Ngưỡng: ')
    },
  )

  it('failed hiển thị message', () => {
    const r = byStatus('failed')
    expect(render(<BreakpointCard attack={attack(r)} />)).toContain(r.message ?? 'thiếu')
  })

  it('cảnh báo sát ngưỡng và không đơn điệu', () => {
    const r = byStatus('non_monotonic')
    expect(r.near_threshold).toBe(true)
    const html = render(<BreakpointCard attack={attack(r)} />)
    expect(html).toContain(NEAR_THRESHOLD)
    expect(html).toContain(NON_MONOTONIC)
    const found = render(<BreakpointCard attack={attack(byStatus('found'))} />)
    expect(found).not.toContain(NEAR_THRESHOLD)
    expect(found).not.toContain(NON_MONOTONIC)
  })

  it('đang chạy: dòng tiến độ (task 30); chưa có điểm: đang chờ', () => {
    const running = byStatus(null)
    const html = render(<BreakpointCard attack={attack(running)} />)
    expect(html).toContain('data-testid="tien-do-tim-nguong"')
    expect(html).toContain(progressText(running) ?? 'thiếu')
    expect(html).toContain('data-status="running"')
    const waiting = render(<BreakpointCard attack={attack(null)} />)
    expect(waiting).toContain('Chưa có điểm nào.')
    expect(waiting).toContain('data-status="queued"')
    expect(waiting).not.toContain('tien-do-tim-nguong')
  })
})

describe('quỹ đạo (task 28)', () => {
  it('bảng số liệu: thứ tự, phạm vi, mức sụt, KTC, điểm tổng hợp; chú giải ký hiệu', () => {
    const r = byStatus('found')
    const html = render(<SearchTrajectory attack={attack(r)} />)
    expect(html).toContain('Quỹ đạo tìm ngưỡng của pgd_linf')
    expect(html.match(/<tr class="border-t"/g)).toHaveLength(r.trajectory.length)
    expect(html).toContain('data-scope="subset"')
    expect(html).toContain('data-scope="full"')
    expect(html).toContain('Tổng hợp (không chạy)')
    expect(html).toContain('Mức sụt tương đối')
    expect(html).toContain(TRAJECTORY_LEGEND)
    const withCi = r.trajectory.find((p) => p.drop_ci)
    if (withCi?.drop_ci) expect(html).toContain(`${(withCi.drop_ci[0] * 100).toFixed(1)}%–`)
  })

  it('chưa có kết quả thì không vẽ', () => {
    expect(render(<SearchTrajectory attack={attack(null)} />)).toBe('')
  })
})

describe('so sánh điểm gãy (task 29)', () => {
  it('bảng có nhãn "> 100%" và "≤ mức nhỏ nhất", badge trạng thái', () => {
    const html = render(
      <BreakpointComparison
        attacks={[
          byStatus('found'),
          byStatus('not_reached'),
          byStatus('below_min'),
          byStatus('failed'),
        ].map(attack)}
      />,
    )
    expect(html).toContain(escape(NOT_REACHED_LABEL))
    expect(html).toContain(BELOW_MIN_LABEL)
    expect(html).toContain('So sánh điểm gãy')
    expect(html).toContain('data-status="failed"')
  })
})
