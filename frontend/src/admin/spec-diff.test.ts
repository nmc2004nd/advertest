import { describe, expect, it } from 'vitest'

import { listMocks } from '@/api/mocks'
import type { AttackSpecAdminPage } from '@/contracts/api'

import { specChanges } from './spec-diff'

const catalog = listMocks<AttackSpecAdminPage>('attack_spec_admin_page')[0].items
const snow = catalog.find((s) => s.name === 'snow')

describe('specChanges (duyệt spec, khác biệt với version đang dùng)', () => {
  if (!snow) throw new Error('Thiếu snow')

  it('spec giống hệt: không có khác biệt; adapter null và adapter suy ra coi như nhau', () => {
    expect(specChanges(snow, snow)).toEqual([])
    expect(specChanges(snow, { ...snow, adapter: 'corruption.imagecorruptions' })).toEqual([])
  })

  it('liệt kê đúng trường đổi, tham số cố định theo từng khóa', () => {
    const next = {
      ...snow,
      primary_param: { ...snow.primary_param, max: 3, values: [1, 2, 3] },
      fixed_params: { corruption: 'snow' },
    }
    expect(specChanges(snow, next)).toEqual([
      { field: 'primary_param.max', before: '5', after: '3' },
      { field: 'primary_param.values', before: '[1,2,3,4,5]', after: '[1,2,3]' },
      { field: 'fixed_params.applied_to', before: '"image_region"', after: '—' },
    ])
  })
})
