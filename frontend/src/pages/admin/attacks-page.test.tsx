import { describe, expect, it } from 'vitest'

import { listMocks, mockMe } from '@/api/mocks'
import { ACCESS_LABEL, fixedParamLines, primaryText } from '@/admin/attack-format'
import { ATTACK_CATALOG_KEY } from '@/admin/useAttackCatalog'
import { can } from '@/auth/permissions'
import type { AttackSpecAdminPage } from '@/contracts/api'
import { splitTabs, visibleNav } from '@/nav/config'
import { render } from '@/test-utils'

import { AttacksPage } from './AttacksPage'

const page = listMocks<AttackSpecAdminPage>('attack_spec_admin_page')[0]

function renderPage(data: AttackSpecAdminPage): string {
  return render(<AttacksPage />, '/admin/attacks', 'admin', [
    [ATTACK_CATALOG_KEY, { pages: [data], pageParams: [null] }],
  ])
}

describe('/admin/attacks (Phase 6, task 35)', () => {
  it('đủ spec của catalog, cả bảng (từ xl) và thẻ (dưới xl)', () => {
    expect(page.items).toHaveLength(10)
    const html = renderPage(page)
    expect(html).toMatch(/<div class="hidden overflow-x-auto[^"]*xl:block"/)
    expect(html).toMatch(/<ul class="flex flex-col gap-3 xl:hidden"/)
    const cards = html.slice(html.indexOf('<ul class="flex flex-col gap-3 xl:hidden"'))
    expect(cards.match(/<li class="flex flex-col gap-2 rounded-xl/g)).toHaveLength(10)
    for (const spec of page.items) {
      expect(html).toContain(spec.name)
      expect(html).toContain(`title="${spec.spec_sha256}"`) // hash rút gọn, đầy đủ trong title
      expect(html).toContain(primaryText(spec))
    }
    expect(html).toContain(ACCESS_LABEL.not_applicable)
    expect(html).not.toContain('Tải thêm')
  })

  it('spec đã tắt có nhãn; còn trang sau thì có "Tải thêm"', () => {
    const [first, ...rest] = page.items
    const html = renderPage({
      items: [{ ...first, is_active: false }, ...rest],
      next_cursor: 'tiep',
    })
    expect(html.split('Đã tắt')).toHaveLength(3) // bảng và thẻ
    expect(html).toContain('Tải thêm')
  })

  it('tham số cố định dạng khóa = giá trị', () => {
    const fgsm = page.items.find((s) => s.name === 'fgsm')
    if (!fgsm) throw new Error('Thiếu fgsm')
    expect(fixedParamLines(fgsm)).toEqual(
      Object.entries(fgsm.fixed_params).map(([k, v]) => `${k} = ${JSON.stringify(v)}`),
    )
  })

  it('chỉ admin có mục điều hướng; điện thoại 3 mục + "Thêm"', () => {
    expect(can(mockMe('admin'), 'attack_catalog.manage')).toBe(true)
    expect(can(mockMe('engineer'), 'attack_catalog.manage')).toBe(false)
    expect(visibleNav(mockMe('engineer')).map((i) => i.path)).not.toContain('/admin/attacks')
    const { tabs, more } = splitTabs(visibleNav(mockMe('admin')))
    expect(tabs).toHaveLength(3)
    expect(more.map((i) => i.path)).toContain('/admin/attacks')
  })
})
