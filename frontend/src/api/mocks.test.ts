import { describe, expect, it } from 'vitest'

import type {
  ExperimentDetail,
  FailureCaseView,
  RunResultOutput as RunResult,
  RunView,
  SliceSummary,
} from '@/contracts/api'
import { runStatusValues } from '@/contracts/schemas'

import { listMocks, mockGet } from './mocks'

describe('mock từ contracts/mocks', () => {
  it('có RunResult cho mọi RunStatus', () => {
    const statuses = new Set(listMocks<RunResult>('run_result').map((r) => r.status))
    expect([...statuses].sort()).toEqual([...runStatusValues].sort())
  })

  it('GET /health trả mock trạng thái ok', () => {
    expect(mockGet('/health')).toMatchObject({ status: 'ok' })
  })

  it('GET /runs/{id} trả đúng run', () => {
    const run = listMocks<RunResult>('run_result')[0]
    expect(mockGet(`/runs/${run.run_id}`)).toEqual(run)
  })

  it('GET /runs/{id} ưu tiên RunView (Phase 5)', () => {
    const view = listMocks<RunView>('run_view')[0]
    expect(mockGet(`/runs/${view.run_id}`)).toEqual(view)
  })

  it('Phase 5: experiment, run, failure case, tài nguyên wizard', () => {
    const detail = listMocks<ExperimentDetail>('experiment_detail')[0]
    expect(mockGet(`/experiments/${detail.id}`)).toEqual(detail)
    const runs = mockGet(`/experiments/${detail.id}/runs`) as RunView[]
    expect(runs.length).toBeGreaterThan(0)
    expect(runs.every((r) => r.experiment_id === detail.id)).toBe(true)
    expect(mockGet('/experiments?owner=me&limit=20')).toHaveProperty('items')
    const cases = listMocks<FailureCaseView>('failure_case_view')
    const listed = mockGet(`/runs/${cases[0].run_id}/failure-cases`) as FailureCaseView[]
    expect(new Set(listed.map((c) => c.id)).size).toBe(listed.length)
    expect(mockGet(`/failure-cases/${cases[0].id}`)).toHaveProperty('display_mode')
    for (const path of [
      '/models',
      '/datasets',
      '/attack-specs',
      '/protocols',
      '/compute-targets',
    ]) {
      expect((mockGet(path) as unknown[]).length).toBeGreaterThan(0)
    }
    const slices = listMocks<SliceSummary>('slice_summary')
    const filtered = mockGet(`/slices?dataset_version=${slices[0].dataset_version_id}`)
    expect(filtered).toEqual(
      slices.filter((x) => x.dataset_version_id === slices[0].dataset_version_id),
    )
  })

  it('đường dẫn không có mock thì báo lỗi rõ ràng', () => {
    expect(() => mockGet('/users')).toThrow('Không có mock cho GET /users')
  })
})
