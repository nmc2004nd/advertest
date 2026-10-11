import { describe, expect, it } from 'vitest'

import type { ExperimentStatus, ReportView, ReviewView, RunCounts } from '@/contracts/api'

import { lifecycle, type LifecycleInput, type LifecycleState } from './lifecycle'

const COUNTS: RunCounts = {
  queued: 0,
  running: 0,
  completed: 3,
  failed: 0,
  skipped: 0,
  stopped_limit: 0,
  cancelled: 0,
}

// Chỉ các trường mà hàm vòng đời đọc.
const review = (decision: ReviewView['decision'], assignee = true) =>
  ({ decision, assignee: assignee ? { id: 'r' } : null }) as unknown as ReviewView
const report = (status: ReportView['status']) => ({ status }) as unknown as ReportView

function input(
  status: ExperimentStatus,
  extra: Partial<LifecycleInput> = {},
  mode: LifecycleInput['mode'] = 'official',
): LifecycleInput {
  return { status, mode, run_counts: COUNTS, review: null, report: null, ...extra }
}

const states = (e: LifecycleInput) =>
  Object.fromEntries(lifecycle(e).map((s) => [s.id, s.state])) as Record<string, LifecycleState>

type Row = [string, LifecycleInput, LifecycleState[]]

// Thứ tự cột: create, run, analyze, submit, review, report.
const OFFICIAL: Row[] = [
  ['draft', input('draft'), ['done', 'todo', 'todo', 'todo', 'todo', 'todo']],
  ['queued', input('queued'), ['done', 'current', 'todo', 'todo', 'todo', 'todo']],
  ['running', input('running'), ['done', 'current', 'todo', 'todo', 'todo', 'todo']],
  ['completed', input('completed'), ['done', 'done', 'current', 'todo', 'todo', 'todo']],
  [
    'completed, có run thất bại',
    input('completed', { run_counts: { ...COUNTS, failed: 2 } }),
    ['done', 'failed', 'current', 'todo', 'todo', 'todo'],
  ],
  ['cancelled', input('cancelled'), ['done', 'done', 'current', 'todo', 'todo', 'todo']],
  [
    'submitted_for_review, chưa ai nhận',
    input('submitted_for_review', { review: review(null, false) }),
    ['done', 'done', 'done', 'done', 'current', 'todo'],
  ],
  [
    'in_review',
    input('in_review', { review: review(null) }),
    ['done', 'done', 'done', 'done', 'current', 'todo'],
  ],
  [
    'changes_requested',
    input('changes_requested', { review: review('changes_requested') }),
    ['done', 'done', 'done', 'done', 'failed', 'todo'],
  ],
  [
    'rejected',
    input('rejected', { review: review('reject') }),
    ['done', 'done', 'done', 'done', 'failed', 'todo'],
  ],
  [
    'approved, chưa có report',
    input('approved', { review: review('approve') }),
    ['done', 'done', 'done', 'done', 'done', 'current'],
  ],
  [
    'approved, report generating',
    input('approved', { review: review('approve'), report: report('generating') }),
    ['done', 'done', 'done', 'done', 'done', 'current'],
  ],
  [
    'approved, report ready',
    input('approved', { review: review('approve'), report: report('ready') }),
    ['done', 'done', 'done', 'done', 'done', 'done'],
  ],
  [
    'approved, report failed',
    input('approved', { review: review('approve'), report: report('failed') }),
    ['done', 'done', 'done', 'done', 'done', 'failed'],
  ],
]

const STEPS = ['create', 'run', 'analyze', 'submit', 'review', 'report']

describe('thanh vòng đời: experiment Chính thức có 6 bước', () => {
  it.each(OFFICIAL)('%s', (_, e, expected) => {
    expect(states(e)).toEqual(Object.fromEntries(STEPS.map((id, i) => [id, expected[i]])))
  })

  it('yêu cầu sửa dùng tông cảnh báo, từ chối dùng tông lỗi', () => {
    const changes = lifecycle(input('changes_requested', { review: review('changes_requested') }))
    const rejected = lifecycle(input('rejected', { review: review('reject') }))
    expect(changes.find((s) => s.id === 'review')?.warning).toBe(true)
    expect(rejected.find((s) => s.id === 'review')?.warning).toBeUndefined()
  })

  it('bước Chạy thất bại nói số run thất bại', () => {
    const steps = lifecycle(input('completed', { run_counts: { ...COUNTS, failed: 2 } }))
    expect(steps.find((s) => s.id === 'run')?.detail).toBe('2 run thất bại')
  })
})

describe('thanh vòng đời: experiment Khám phá chỉ có 3 bước', () => {
  const rows: [ExperimentStatus, LifecycleState[]][] = [
    ['draft', ['done', 'todo', 'todo']],
    ['queued', ['done', 'current', 'todo']],
    ['running', ['done', 'current', 'todo']],
    ['completed', ['done', 'done', 'current']],
    ['cancelled', ['done', 'done', 'current']],
  ]
  it.each(rows)('%s', (status, expected) => {
    const steps = lifecycle(input(status, {}, 'exploration'))
    expect(steps.map((s) => s.id)).toEqual(['create', 'run', 'analyze'])
    expect(steps.map((s) => s.state)).toEqual(expected)
  })
})
