import { describe, expect, it } from 'vitest'

import { listMocks } from '@/api/mocks'
import type { RunView } from '@/contracts/api'

import { runLabel } from './format'

const base = listMocks<RunView>('run_view')[0]
if (!base) throw new Error('Thiếu mock run_view')

function withParam(paramName: string, paramUnit: string, level: number): RunView {
  return {
    ...base,
    level,
    attack_spec: { ...base.attack_spec, name: 'fog', param_name: paramName, param_unit: paramUnit },
  }
}

describe('nhãn run', () => {
  it('bỏ đơn vị khi trùng tên tham số (fog: không lặp "severity")', () => {
    expect(runLabel(withParam('severity', 'severity', 2))).toBe('fog · severity 2')
  })

  it('giữ đơn vị khi khác tên tham số', () => {
    expect(runLabel(withParam('epsilon', '1/255', 8))).toBe('fog · epsilon 8 1/255')
  })
})
