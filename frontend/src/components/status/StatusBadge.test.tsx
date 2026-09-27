import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import { experimentStatusValues, runStatusValues, searchStatusValues } from '@/contracts/schemas'

import { StatusBadge } from './StatusBadge'
import {
  EXPERIMENT_STATUS,
  RUN_STATUS,
  SEARCH_STATUS,
  type StatusBadgeProps,
  type StatusDisplay,
  TONE_CLASS,
} from './status-config'

interface KindCase {
  kind: StatusBadgeProps['kind']
  values: readonly string[]
  config: Record<string, StatusDisplay>
}

const KINDS: KindCase[] = [
  { kind: 'run', values: runStatusValues, config: RUN_STATUS },
  { kind: 'experiment', values: experimentStatusValues, config: EXPERIMENT_STATUS },
  { kind: 'search', values: searchStatusValues, config: SEARCH_STATUS },
]

describe.each(KINDS)('StatusBadge kind=$kind', ({ kind, values, config }) => {
  it('cấu hình có đúng tập giá trị của enum trong contract, không thừa không thiếu', () => {
    expect(Object.keys(config).sort()).toEqual([...values].sort())
  })

  it('mỗi giá trị có nhãn và icon riêng, tông màu hợp lệ', () => {
    const entries = values.map((v) => config[v])
    expect(new Set(entries.map((e) => e.label)).size).toBe(values.length)
    expect(new Set(entries.map((e) => e.icon)).size).toBe(values.length)
    for (const entry of entries) {
      expect(entry.label.trim()).not.toBe('')
      expect(Object.keys(TONE_CLASS)).toContain(entry.tone)
    }
  })

  it.each([...values])('render %s bằng màu + icon + chữ', (status) => {
    const props = { kind, status } as StatusBadgeProps
    const html = renderToStaticMarkup(<StatusBadge {...props} />)
    const display = config[status]
    expect(html).toContain(display.label)
    expect(html).toContain('<svg')
    expect(html).toContain(`data-status="${status}"`)
    expect(html).toContain(`data-tone="${display.tone}"`)
  })
})
