import { House } from 'lucide-react'
import { describe, expect, it } from 'vitest'

import { mockMe } from '@/api/mocks'

import { MAX_TABS, NAV_ITEMS, splitTabs, visibleNav, type NavItem } from './config'

function item(path: string, overrides: Partial<NavItem> = {}): NavItem {
  return {
    path,
    label: path,
    icon: House,
    requirement: 'authenticated',
    implemented: true,
    ...overrides,
  }
}

describe('visibleNav', () => {
  it('ẩn mục chưa có trang', () => {
    const items = [item('/a'), item('/b', { implemented: false })]
    expect(visibleNav(mockMe('engineer'), items).map((i) => i.path)).toEqual(['/a'])
  })

  it('ẩn mục thiếu quyền', () => {
    const items = [item('/users', { requirement: 'user.manage' }), item('/me')]
    expect(visibleNav(mockMe('engineer'), items).map((i) => i.path)).toEqual(['/me'])
    expect(visibleNav(mockMe('admin'), items).map((i) => i.path)).toEqual(['/users', '/me'])
    expect(visibleNav(null, items)).toEqual([])
  })

  it('đường dẫn trong cấu hình không trùng', () => {
    const paths = NAV_ITEMS.map((i) => i.path)
    expect(new Set(paths).size).toBe(paths.length)
  })
})

describe('splitTabs', () => {
  it(`không quá ${MAX_TABS} mục thì hiện hết, không có "Thêm"`, () => {
    const items = ['/a', '/b', '/c', '/d'].map((p) => item(p))
    expect(splitTabs(items)).toEqual({ tabs: items, more: [] })
  })

  it('dư thì 3 mục đầu và "Thêm" chứa phần còn lại', () => {
    const items = ['/a', '/b', '/c', '/d', '/e'].map((p) => item(p))
    const { tabs, more } = splitTabs(items)
    expect(tabs.map((i) => i.path)).toEqual(['/a', '/b', '/c'])
    expect(more.map((i) => i.path)).toEqual(['/d', '/e'])
  })
})
