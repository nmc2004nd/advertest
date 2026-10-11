// validation.md Phase R3, Group 5: hàm sinh câu của từng biểu đồ, bảng dữ liệu → câu.
import { describe, expect, it } from 'vitest'

import type { AttackRankingEntry, RobustnessRow } from '@/contracts/api'

import type { ComparisonRow } from './breakpoints'
import type { AttackCurve, CurvePoint } from './curves'
import {
  bandLabel,
  breakpointSentence,
  curveSentence,
  dropTone,
  matrixSentence,
  rankingSentence,
} from './sentences'

const BANDS: [number, number][] = [
  [0, 0.25],
  [0.25, 0.5],
  [0.5, 0.75],
  [0.75, 1],
]

function point(level: number, relativeDrop: number | null): CurvePoint {
  return {
    runId: `r${level}`,
    level,
    status: 'completed',
    map50: null,
    asr: null,
    relativeDrop,
    partial: false,
    earlyStop: false,
  }
}

function curve(points: CurvePoint[]): AttackCurve {
  return {
    attackSpecId: 'a',
    name: 'fgsm',
    version: 1,
    paramName: 'eps',
    paramUnit: '1/255',
    paramMax: 32,
    points,
  }
}

function row(name: string, drops: (number | null)[]): RobustnessRow {
  return {
    attack_spec_id: name,
    attack_name: name,
    cells: drops.map((d, band) => ({ band, max_relative_drop: d, runs: d === null ? 0 : 1 })),
  }
}

function entry(name: string, auc: number | null): AttackRankingEntry {
  return {
    attack_spec_id: name,
    name,
    kind: 'attack',
    auc_drop: auc,
    max_relative_drop: null,
    levels_evaluated: 3,
    levels_early_stopped: 0,
    coverage: 1,
    partial: false,
  } as AttackRankingEntry
}

describe('đường mức sụt', () => {
  it.each([
    [
      [point(2, 0.05), point(4, 0.35), point(8, 0.7)],
      'fgsm: từ eps 4, mAP@0.5 giảm 35%, vượt mức 30%.',
    ],
    [[point(2, 0.05), point(4, 0.18)], 'fgsm: mức sụt lớn nhất 18% ở eps 4, chưa tới 30%.'],
    [[point(2, 0.01), point(4, 0.04)], 'fgsm: mAP@0.5 giảm dưới 10% ở mọi level đã chạy.'],
    [[point(2, null)], 'fgsm: chưa có level nào có metric.'],
  ])('%j → câu', (points, expected) => {
    expect(curveSentence(curve(points))).toBe(expected)
  })
})

describe('xếp hạng attack', () => {
  it.each([
    [
      [entry('pgd', 0.61), entry('fog', 0.12), entry('snow', null)],
      'pgd gây hại nhiều nhất trên toàn dải (auc_drop 0.61), fog ít nhất (0.12).',
    ],
    [[entry('pgd', 0.4), entry('fog', null)], 'Mới có pgd đủ dữ liệu: diện tích mức sụt 0.40.'],
    [[entry('fog', null)], 'Chưa attack nào đủ dữ liệu để xếp hạng.'],
  ])('%j → câu', (ranking, expected) => {
    expect(rankingSentence(ranking)).toBe(expected)
  })
})

describe('so sánh điểm gãy', () => {
  const r = (
    name: string,
    status: ComparisonRow['status'],
    value: number | null,
    label: string,
  ) => ({
    attackSpecId: name,
    name,
    status,
    value,
    label,
  })
  it.each([
    [
      [
        r('pgd', 'found', 12.5, '12.5%'),
        r('fgsm', 'found', 40, '40%'),
        r('fog', 'not_reached', 100, '> 100%'),
      ],
      'pgd làm model gãy sớm nhất, ở 12.5% dải của spec; 1 attack khác gãy muộn hơn.',
    ],
    [[r('pgd', 'non_monotonic', 30, '30%')], 'pgd làm model gãy sớm nhất, ở 30% dải của spec.'],
    [
      [r('fog', 'below_min', 0, '≤ mức nhỏ nhất')],
      'fog làm model gãy ngay ở mức nhỏ nhất của dải tìm kiếm.',
    ],
    [[r('fog', 'not_reached', 100, '> 100%')], 'Chưa attack nào làm model gãy trong dải tìm kiếm.'],
    [[r('fog', null, null, '—')], 'Chưa có điểm gãy nào: tìm ngưỡng chưa xong.'],
  ])('%j → câu', (rows, expected) => {
    expect(breakpointSentence(rows)).toBe(expected)
  })
})

describe('ma trận độ bền', () => {
  it.each([
    [
      [row('fgsm', [0.42, 0.71, null, null]), row('fog', [null, 0.05, 0.18, 0.33])],
      'Sụt nặng nhất 71% (fgsm ở dải 25–50% dải); 2/2 attack có dải sụt từ 30% trở lên.',
    ],
    [
      [row('fog', [0.05, 0.12, 0.2, null])],
      'Mức sụt lớn nhất là 20% (fog ở dải 50–75% dải), chưa attack nào tới 30%.',
    ],
    [[row('fog', [0.01, 0.02, null, null])], 'Mọi attack đã chạy đều sụt dưới 10% ở mọi dải.'],
    [[row('fog', [null, null, null, null])], 'Chưa dải nào có run có metric.'],
  ])('%j → câu', (rows, expected) => {
    expect(matrixSentence(rows, BANDS)).toBe(expected)
  })

  it('tên hiển thị thay tên kỹ thuật', () => {
    expect(
      matrixSentence([row('fog', [0.6, null, null, null])], BANDS, () => 'Sương mù'),
    ).toContain('Sương mù ở dải 0–25% dải')
  })

  it('nhãn dải và thang màu (design.md mục 3)', () => {
    expect(BANDS.map(bandLabel)).toEqual(['0–25% dải', '25–50% dải', '50–75% dải', '75–100% dải'])
    expect([null, 0.05, 0.1, 0.29, 0.3, 0.49, 0.5, 1].map(dropTone)).toEqual([
      'empty',
      'none',
      'low',
      'low',
      'mid',
      'mid',
      'high',
      'high',
    ])
  })
})
