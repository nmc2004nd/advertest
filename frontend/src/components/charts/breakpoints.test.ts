import { describe, expect, it } from 'vitest'

import { listMocks } from '@/api/mocks'
import type { AttackSpec, ExperimentDetail, RunView, SearchResult } from '@/contracts/api'

import {
  BELOW_MIN_LABEL,
  comparisonRows,
  conclusion,
  formatLevel,
  formatRange,
  gridAttackIds,
  formatExact,
  formatNumber,
  notReachedLabel,
  progressText,
  type SearchAttack,
  searchAttacks,
  type SpecInfo,
  specInfoMap,
  thresholdText,
  trajectoryRows,
} from './breakpoints'

const catalog = listMocks<AttackSpec>('attack_spec')
const results = listMocks<SearchResult>('search_result')
const specs = specInfoMap([], catalog)

function result(status: SearchResult['status'] | 'running'): SearchResult {
  const found = results.find((r) =>
    status === 'running' ? r.status === null : r.status === status,
  )
  if (!found) throw new Error(`Thiếu mock search_result ${String(status)}`)
  return found
}

const FGSM: SpecInfo = { name: 'fgsm', paramName: 'eps', paramUnit: '1/255', paramMax: 32 }
const SEVERITY: SpecInfo = { name: 'x', paramName: 'severity', paramUnit: 'severity', paramMax: 5 }

/** Attack từ một mock kết quả; dải cấu hình 0–max của spec (hoặc theo `range`). */
function attack(
  r: SearchResult | null,
  spec: SpecInfo | null,
  range?: [number, number],
): SearchAttack {
  const [lo, hi] = range ?? [0, spec?.paramMax ?? 1]
  return {
    attackSpecId: r?.attack_spec_id ?? 'khong-co',
    spec,
    config: {
      threshold_kind: r?.threshold_kind ?? 'relative_drop',
      threshold: r?.threshold ?? 0.2,
      lo,
      hi,
      tol: (hi - lo) / 256,
      coarse_n: 4,
      subset_size: 100,
      class_filter: r?.class_filter ?? null,
      bootstrap_samples: 200,
    },
    result: r,
  }
}

const withSpec = (r: SearchResult, range?: [number, number]) =>
  attack(r, specs.get(r.attack_spec_id) ?? FGSM, range)

describe('định dạng', () => {
  it('đơn vị 1/255 viết liền, đơn vị khác sau dấu cách, bỏ số 0 thừa', () => {
    expect(formatLevel(6.5, '1/255')).toBe('6.5/255')
    expect(formatLevel(0.0625, 'L2')).toBe('0.0625 L2')
    expect(formatLevel(3, '')).toBe('3')
    expect(formatRange(0, 32, '1/255')).toBe('0–32/255')
    expect(formatRange(0.1, 0.9, 'ratio')).toBe('0.1–0.9 ratio')
  })

  it('làm tròn 4 chữ số có nghĩa cho câu kết luận; bảng giữ giá trị chính xác (review Group 6 #2)', () => {
    expect(formatNumber(1.0625)).toBe('1.063')
    expect(formatNumber(16.5)).toBe('16.5')
    expect(formatNumber(0.375)).toBe('0.375')
    expect(formatExact(1.0625)).toBe('1.0625')
    expect(formatExact(0.1 + 0.2)).toBe('0.3')
  })

  it('ngưỡng: loại, %, class', () => {
    expect(
      thresholdText({ threshold_kind: 'relative_drop', threshold: 0.2, class_filter: null }),
    ).toBe('Ngưỡng: mức sụt tương đối 20%')
    expect(
      thresholdText({
        threshold_kind: 'attack_success_rate',
        threshold: 0.5,
        class_filter: 'person',
      }),
    ).toBe('Ngưỡng: tỷ lệ tấn công thành công 50% (class person)')
  })
})

describe('câu kết luận theo trạng thái (task 27)', () => {
  it('found: điểm gãy kèm khoảng tin cậy 95%', () => {
    expect(conclusion(withSpec(result('found')))).toBe(
      'Gãy tại eps ≈ 0.5/255, KTC 95%: 0.41–0.5/255',
    )
  })

  it('non_monotonic: điểm gãy (cảnh báo hiển thị riêng); đơn vị trùng tên tham số không lặp', () => {
    const r = result('non_monotonic')
    expect(conclusion(attack(r, SEVERITY))).toBe('Gãy tại severity ≈ 3, KTC 95%: 2.4–3')
  })

  it('found chưa có bootstrap: không có khoảng tin cậy', () => {
    const r = { ...result('found'), confidence_interval: null }
    expect(conclusion(withSpec(r))).toBe('Gãy tại eps ≈ 0.5/255')
  })

  it('not_reached: dải tìm kiếm của cấu hình', () => {
    const r = result('not_reached')
    expect(conclusion(withSpec(r, [0, 0.9]))).toBe('Không gãy trong dải 0–0.9 ratio')
  })

  it('below_min: mức nhỏ nhất của dải', () => {
    expect(conclusion(attack(result('below_min'), FGSM, [2, 32]))).toBe(
      'Gãy ngay ở mức nhỏ nhất (eps = 2/255)',
    )
  })

  it('stopped_limit: khoảng hiện có', () => {
    expect(conclusion(attack(result('stopped_limit'), FGSM))).toBe(
      'Dừng do giới hạn trước khi kết luận: khoảng hiện có 1–2/255',
    )
  })

  it('failed: hiển thị message', () => {
    const r = result('failed')
    expect(conclusion(withSpec(r))).toBe(r.message)
  })

  it('đang chạy và chưa có điểm', () => {
    expect(conclusion(withSpec(result('running')))).toBe('Đang tìm: khoảng hiện tại 0–1/255.')
    expect(conclusion(attack(null, FGSM))).toBe('Chưa có điểm nào.')
  })
})

describe('dòng tiến độ (task 30)', () => {
  it('đang chạy: điểm / tối đa, khoảng hiện tại, giai đoạn', () => {
    expect(progressText(result('running'))).toBe(
      'Điểm 7 / tối đa 23 · khoảng hiện tại [0, 1] · giai đoạn: chia đôi trên tập con',
    )
  })

  it('xong hoặc chưa có kết quả: không có dòng tiến độ', () => {
    expect(progressText(result('found'))).toBeNull()
    expect(progressText(null)).toBeNull()
  })
})

describe('quỹ đạo', () => {
  it('sắp theo thứ tự đánh giá', () => {
    const r = result('found')
    const shuffled = { ...r, trajectory: [...r.trajectory].reverse() }
    expect(trajectoryRows(shuffled).map((p) => p.order)).toEqual(
      r.trajectory.map((p) => p.order).sort((x, y) => x - y),
    )
  })
})

describe('so sánh điểm gãy (task 29)', () => {
  it('chuẩn hóa level / max, tăng dần; not_reached "> 100%", below_min "≤ mức nhỏ nhất"; không cột xếp cuối', () => {
    const rows = comparisonRows([
      attack(result('failed'), FGSM),
      attack(result('not_reached'), { ...FGSM, name: 'chua' }),
      attack(result('found'), { ...FGSM, name: 'gay' }),
      attack(result('below_min'), { ...FGSM, name: 'ngay' }, [2, 32]),
      attack(result('stopped_limit'), { ...FGSM, name: 'dung' }),
      attack(null, { ...FGSM, name: 'cho' }),
    ])
    expect(rows.map((r) => [r.name, r.value, r.label])).toEqual([
      ['ngay', 6.25, BELOW_MIN_LABEL],
      ['gay', (0.5 / 32) * 100, '1.6%'],
      ['chua', 100, '> 100%'],
      ['fgsm', null, 'Thất bại'],
      ['dung', null, 'Dừng do giới hạn: chưa có điểm gãy'],
      ['cho', null, 'Chưa có điểm'],
    ])
  })

  it('not_reached trên dải tìm kiếm hẹp: "> hi/max", cột tới hi (review Group 6 #1)', () => {
    const narrow = attack(result('not_reached'), FGSM, [0, 8])
    const [row] = comparisonRows([narrow])
    expect(row).toMatchObject({ value: 25, label: '> 25%' })
    expect(notReachedLabel(32, 32)).toBe('> 100%')
    expect(notReachedLabel(8, undefined)).toBe('Không gãy trong dải tìm kiếm')
  })

  it('không biết spec thì không vẽ cột', () => {
    const [row] = comparisonRows([attack(result('found'), null)])
    expect(row.value).toBeNull()
    expect(row.name).toMatch(/^Attack /)
  })
})

describe('ghép với experiment', () => {
  const detail = listMocks<ExperimentDetail>('experiment_detail').find(
    (e) => e.status === 'completed' && (e.search_results ?? []).length > 0,
  )
  if (!detail) throw new Error('Thiếu mock experiment tìm ngưỡng đã xong')

  it('mỗi attack tìm ngưỡng của cấu hình một mục, ghép kết quả; attack quét lưới tách riêng', () => {
    const list = searchAttacks(detail, specs)
    const searchIds = detail.config.attacks
      .filter((a) => a.mode === 'search')
      .map((a) => a.attack_spec_id)
    expect(list.map((a) => a.attackSpecId)).toEqual(searchIds)
    expect(list.every((a) => a.result?.attack_spec_id === a.attackSpecId)).toBe(true)
    expect([...gridAttackIds(detail)]).toEqual(
      detail.config.attacks.filter((a) => a.mode === 'grid').map((a) => a.attack_spec_id),
    )
  })

  it('spec ưu tiên thông tin của run (phiên bản đã chạy), không có run thì lấy catalog', () => {
    const pgd = catalog.find((s) => s.name === 'pgd_linf')
    if (!pgd) throw new Error('Thiếu mock pgd_linf')
    const run = {
      attack_spec_id: pgd.id,
      attack_spec: {
        name: 'pgd_cu',
        version: 1,
        param_name: 'eps',
        param_unit: '1/255',
        param_max: 16,
      },
    } as RunView
    expect(specInfoMap([], catalog).get(pgd.id)?.paramMax).toBe(32)
    expect(specInfoMap([run], catalog).get(pgd.id)).toEqual({
      name: 'pgd_cu',
      paramName: 'eps',
      paramUnit: '1/255',
      paramMax: 16,
    })
  })
})
