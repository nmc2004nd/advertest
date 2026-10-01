import { describe, expect, it } from 'vitest'

import { listMocks } from '@/api/mocks'
import type { ExperimentDetail, RunView } from '@/contracts/api'
import { RunsTable } from '@/features/experiments/tabs'
import { EARLY_STOP_TEXT, reasonText } from '@/features/experiments/format'
import { render } from '@/test-utils'

import { AttackRanking } from './AttackRanking'
import { formatAuc, levelsText, NO_DATA } from './ranking'

const detail = listMocks<ExperimentDetail>('experiment_detail').find(
  (d) => (d.attack_ranking ?? []).length >= 10,
)
if (!detail) throw new Error('Thiếu mock experiment toàn catalog')
const ranking = detail.attack_ranking ?? []
const runs = listMocks<RunView>('run_view').filter((r) => r.experiment_id === detail.id)

describe('xếp hạng attack (Phase 6, task 32)', () => {
  it('bảng giữ thứ tự của backend, đủ cột, null ghi "không đủ dữ liệu"', () => {
    const html = render(<AttackRanking ranking={ranking} />)
    const table = html.slice(html.indexOf('<table'), html.indexOf('</table>'))
    const names = [...table.matchAll(/<td class="px-3 py-2 font-medium">([^<]+)</g)].map(
      (m) => m[1],
    )
    expect(names).toEqual(ranking.map((e) => e.name))
    for (const header of ['auc_drop', 'Mức sụt lớn nhất', 'Số level', 'Độ phủ']) {
      expect(table).toContain(header)
    }
    const none = ranking.filter((e) => e.auc_drop === null)
    expect(none.length).toBeGreaterThan(0)
    expect(table.split(NO_DATA)).toHaveLength(none.length + 1)
    // Độ phủ hiển thị dạng phần trăm.
    expect(table).toContain('12.5%')
  })

  it('điện thoại: danh sách thẻ (bảng chỉ hiện từ md)', () => {
    const html = render(<AttackRanking ranking={ranking} />)
    expect(html).toMatch(/<div class="hidden overflow-x-auto[^"]*md:block"/)
    expect(html).toMatch(/<ol class="flex flex-col gap-3 md:hidden"/)
    expect(html.match(/<li class="flex flex-col gap-1 rounded-xl border/g)).toHaveLength(
      ranking.length,
    )
  })

  it('số level kèm level dừng sớm; cờ partial', () => {
    const stopped = ranking.find((e) => e.levels_early_stopped > 0)
    if (!stopped) throw new Error('Thiếu attack có level dừng sớm')
    expect(levelsText(stopped)).toBe(
      `${stopped.levels_evaluated} (+${stopped.levels_early_stopped} dừng sớm)`,
    )
    expect(formatAuc(null)).toBe(NO_DATA)
    expect(formatAuc(0.91264)).toBe('0.913')
    const html = render(<AttackRanking ranking={ranking} />)
    expect(html).toContain('Có run dừng giữa chừng')
  })

  it('không có attack nào thì không hiện gì', () => {
    expect(render(<AttackRanking ranking={[]} />)).toBe('')
  })
})

describe('nhãn dừng sớm trong bảng run (Phase 6, task 32)', () => {
  const stopped = runs.find((r) => r.status_reason?.code === 'early_stop')
  if (!stopped) throw new Error('Thiếu mock run early_stop')
  const trigger = runs.find((r) => r.run_id === stopped.status_reason?.trigger_run_id)
  if (!trigger) throw new Error('Thiếu run kích hoạt')

  it('ghi rõ đã sụp ở level nào', () => {
    expect(reasonText(stopped, runs)).toBe(
      `${EARLY_STOP_TEXT} (sụp ở ${trigger.attack_spec.param_name} ${trigger.level} ${trigger.attack_spec.param_unit})`,
    )
    expect(reasonText(stopped, [])).toBe(EARLY_STOP_TEXT)
    const failed = runs.find((r) => r.status === 'failed')
    expect(failed && reasonText(failed, runs)).toBe(failed?.status_reason?.message)
  })

  it('bảng run hiển thị nhãn', () => {
    const html = render(<RunsTable runs={runs} />)
    expect(html).toContain(EARLY_STOP_TEXT)
  })
})
