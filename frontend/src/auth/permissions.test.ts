import { describe, expect, it } from 'vitest'

import { listMocks } from '@/api/mocks'
import { ROLE_PERMISSIONS } from '@/contracts/permissions'
import { permissionValues, roleValues, type Me } from '@/contracts/schemas'

import { AUTHENTICATED, can, permissionsFor } from './permissions'

const MES = listMocks<Me>('me')

describe('can', () => {
  it('có mock Me cho từng role và một tổ hợp nhiều role', () => {
    const single = new Set(MES.filter((m) => m.roles.length === 1).map((m) => m.roles[0]))
    expect([...single].sort()).toEqual([...roleValues].sort())
    expect(MES.some((m) => m.roles.length > 1)).toBe(true)
  })

  it.each(MES.map((me) => [me.roles.join('+'), me] as const))(
    'đúng theo ma trận cho %s',
    (_, me) => {
      for (const permission of permissionValues) {
        const expected = me.roles.some((role) => ROLE_PERMISSIONS[role].includes(permission))
        expect(can(me, permission)).toBe(expected)
      }
      // Trùng với permissions do server trả trong mock.
      expect([...permissionsFor(me.roles)].sort()).toEqual([...me.permissions].sort())
      expect(can(me, AUTHENTICATED)).toBe(true)
    },
  )

  it('chưa đăng nhập thì không có quyền nào', () => {
    expect(can(null, AUTHENTICATED)).toBe(false)
    expect(can(undefined, 'experiment.read')).toBe(false)
  })
})
