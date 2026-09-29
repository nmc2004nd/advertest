import { describe, expect, it } from 'vitest'

import { actionsFor } from '@/admin/user-actions'
import { listMocks } from '@/api/mocks'
import type { UserAdminPage, UserAdminView } from '@/contracts/schemas'
import { render } from '@/test-utils'

import { UsersPage } from './UsersPage'

const allPage = listMocks<UserAdminPage>('user_admin_page').find((p) => p.next_cursor)
const pendingPage = listMocks<UserAdminPage>('user_admin_page').find((p) => !p.next_cursor)

function byStatus(status: UserAdminView['status']): UserAdminView {
  const user = allPage?.items.find((u) => u.status === status)
  if (!user) throw new Error(status)
  return user
}

describe('actionsFor', () => {
  it('hành động theo trạng thái', () => {
    expect(actionsFor(byStatus('pending'))).toEqual(['approve', 'reject'])
    expect(actionsFor(byStatus('active'))).toEqual(['roles', 'reset-link', 'disable'])
    expect(actionsFor(byStatus('disabled'))).toEqual(['enable', 'roles', 'reset-link'])
    expect(actionsFor(byStatus('rejected'))).toEqual([])
    // Admin không tự vô hiệu hóa được mình (backend trả 409): ẩn nút với chính mình.
    const active = byStatus('active')
    expect(actionsFor(active, active.id)).toEqual(['roles', 'reset-link'])
  })
})

describe('/admin/users', () => {
  const html = render(<UsersPage />, '/admin/users', 'admin', [
    [['admin', 'users', 'list', 'pending'], { pages: [pendingPage], pageParams: [null] }],
  ])

  it('có tab Chờ duyệt / Tất cả', () => {
    expect(html).toContain('role="tablist"')
    expect(html).toContain('Chờ duyệt')
    expect(html).toContain('Tất cả')
  })

  it('bảng chỉ hiện từ 1280px, thẻ hiện dưới 1280px', () => {
    expect(html).toMatch(/class="hidden [^"]*xl:block"><table/)
    expect(html).toMatch(/<ul class="[^"]*xl:hidden"/)
  })

  it('user chờ duyệt có nút Duyệt và Từ chối, có nhãn rõ cho từng người', () => {
    const user = pendingPage?.items[0]
    expect(html).toContain(`aria-label="Duyệt: ${user?.full_name}"`)
    expect(html).toContain(`aria-label="Từ chối: ${user?.full_name}"`)
  })
})
