import { House } from 'lucide-react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'

import type { NavItem } from '@/nav/config'

import { BottomTabs, MoreLinks, SideNav } from './AppShell'

function items(n: number): NavItem[] {
  return Array.from({ length: n }, (_, i) => ({
    path: `/muc-${i}`,
    label: `Mục ${i}`,
    icon: House,
    requirement: 'authenticated',
    implemented: true,
  }))
}

function render(node: React.ReactNode): string {
  return renderToStaticMarkup(<MemoryRouter>{node}</MemoryRouter>)
}

describe('BottomTabs (điện thoại)', () => {
  it('chỉ hiện dưới 768px và xử lý vùng an toàn', () => {
    const html = render(<BottomTabs items={items(2)} />)
    expect(html).toContain('md:hidden')
    expect(html).toContain('safe-area-inset-bottom')
  })

  it('không quá 4 mục thì không có "Thêm"', () => {
    const html = render(<BottomTabs items={items(4)} />)
    expect(html.match(/href="\/muc-/g)).toHaveLength(4)
    expect(html).not.toContain('Thêm')
  })

  it('dư thì 3 mục và "Thêm"', () => {
    const html = render(<BottomTabs items={items(6)} />)
    expect(html.match(/href="\/muc-/g)).toHaveLength(3)
    expect(html).toContain('Thêm')
  })

  it('mục trong "Thêm" hiện link với class đúng (không bọc Slot làm hỏng className)', () => {
    const html = render(<MoreLinks items={items(6).slice(3)} onNavigate={() => undefined} />)
    expect(html.match(/href="\/muc-/g)).toHaveLength(3)
    expect(html).toContain('min-h-11')
    expect(html).not.toContain('isActive')
  })

  it('không có mục nào thì không hiện thanh tab', () => {
    expect(render(<BottomTabs items={[]} />)).toBe('')
  })
})

describe('SideNav (tablet, desktop)', () => {
  it('ẩn trên điện thoại, cột icon ở tablet, nhãn chỉ hiện từ 1280px', () => {
    const html = render(<SideNav items={items(2)} name="Quản trị viên" />)
    expect(html).toContain('hidden')
    expect(html).toContain('md:flex')
    expect(html).toContain('xl:w-60')
    expect(html).toContain('aria-label="Mục 0"')
  })
})
