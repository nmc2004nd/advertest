import { describe, expect, it } from 'vitest'

import { mockMe, modelMocks } from '@/api/mocks'

import { canManageModel } from './model-owner'

const model = modelMocks()[0]

describe('quyền thao tác trên model', () => {
  it('admin thao tác được mọi model', () => {
    expect(canManageModel({ ...model, owner_id: null }, mockMe('admin'))).toBe(true)
  })

  it('engineer chỉ thao tác được model mình đăng ký', () => {
    const engineer = mockMe('engineer')
    expect(canManageModel({ ...model, owner_id: engineer.id }, engineer)).toBe(true)
    expect(canManageModel({ ...model, owner_id: mockMe('admin').id }, engineer)).toBe(false)
    expect(canManageModel({ ...model, owner_id: null }, engineer)).toBe(false)
    expect(canManageModel(model, undefined)).toBe(false)
  })
})
