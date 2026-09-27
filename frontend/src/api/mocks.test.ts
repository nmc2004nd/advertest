import { describe, expect, it } from 'vitest'

import type { RunResultOutput as RunResult } from '@/contracts/api'
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

  it('đường dẫn không có mock thì báo lỗi rõ ràng', () => {
    expect(() => mockGet('/users')).toThrow('Không có mock cho GET /users')
  })
})
