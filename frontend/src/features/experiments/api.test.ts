import { describe, expect, it } from 'vitest'

import { POLL_INTERVAL_MS } from '@/api/queries'
import { experimentStatusValues, runStatusValues } from '@/contracts/schemas'

import {
  experimentParams,
  experimentPollInterval,
  msUntilUrlRefresh,
  runPollInterval,
  URL_REFRESH_MARGIN_MS,
} from './api'

describe('polling (validation.md: hook polling ngừng khi experiment ở trạng thái cuối)', () => {
  it.each(experimentStatusValues)('experiment %s', (status) => {
    const active = status === 'queued' || status === 'running'
    expect(experimentPollInterval(status)).toBe(active ? POLL_INTERVAL_MS : false)
  })

  it.each(runStatusValues)('run %s', (status) => {
    const active = status === 'queued' || status === 'running'
    expect(runPollInterval(status)).toBe(active ? POLL_INTERVAL_MS : false)
  })

  it('chưa có dữ liệu thì vẫn polling', () => {
    expect(experimentPollInterval(undefined)).toBe(POLL_INTERVAL_MS)
  })
})

describe('xin lại URL ảnh trước khi hết hạn (task 22)', () => {
  const now = Date.parse('2026-09-30T08:00:00Z')

  it('trước hạn 60 giây', () => {
    expect(msUntilUrlRefresh('2026-09-30T08:10:00Z', now)).toBe(10 * 60_000 - URL_REFRESH_MARGIN_MS)
  })

  it('đã quá biên an toàn thì xin lại ngay', () => {
    expect(msUntilUrlRefresh('2026-09-30T08:00:30Z', now)).toBe(0)
  })

  it('ảnh bị ẩn (không có URL) thì không hẹn', () => {
    expect(msUntilUrlRefresh(null, now)).toBeNull()
  })
})

describe('tham số danh sách', () => {
  it('bỏ bộ lọc trống, kèm cursor', () => {
    const params = experimentParams({ owner: 'me', status: '', model: '' }, 'abc')
    expect(Object.fromEntries(params)).toEqual({ owner: 'me', limit: '20', cursor: 'abc' })
    const all = experimentParams({ owner: 'all', status: 'running', model: 'm1' }, null)
    expect(Object.fromEntries(all)).toEqual({
      owner: 'all',
      limit: '20',
      status: 'running',
      model: 'm1',
    })
  })
})
