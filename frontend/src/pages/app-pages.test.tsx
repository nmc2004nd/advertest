import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'

import { listMocks } from '@/api/mocks'
import { ApiError } from '@/api/errors'
import { RequirePermission } from '@/auth/RequirePermission'
import { PENDING_USERS_QUERY_KEY, pendingCountLabel } from '@/auth/pending-count'
import { ME_QUERY_KEY } from '@/auth/useMe'
import type { UserAdminPage } from '@/contracts/schemas'
import { visibleNav } from '@/nav/config'
import { mockMe } from '@/api/mocks'
import { expectLabelledControls, render } from '@/test-utils'

import { AccountPage } from './AccountPage'
import { HomePage } from './HomePage'

const pendingPage = listMocks<UserAdminPage>('user_admin_page').find((p) => !p.next_cursor)

describe('/account', () => {
  it('thông tin, role và 3 ô đổi mật khẩu có nhãn, nút đăng xuất', () => {
    const html = render(<AccountPage />, '/account', 'engineer_reviewer')
    expect(html).toContain('Kỹ sư ML/perception, Kỹ sư an toàn (reviewer)')
    expectLabelledControls(html, 3)
    expect(html).toContain('Đăng xuất')
  })
})

describe('/home', () => {
  it('admin thấy số tài khoản chờ duyệt', () => {
    const html = render(<HomePage />, '/home', 'admin', [[PENDING_USERS_QUERY_KEY, pendingPage]])
    expect(html).toContain('tài khoản chờ duyệt')
    expect(html).toContain(`>${pendingPage?.items.length}<`)
    expect(html).toContain('href="/admin/users"')
  })

  it('engineer và reviewer thấy "Sắp có", không thấy khối admin', () => {
    const html = render(<HomePage />, '/home', 'engineer_reviewer')
    expect(html.match(/Sắp có/g)).toHaveLength(2)
    expect(html).not.toContain('chờ duyệt')
  })

  it('nhãn đếm có dấu + khi còn trang sau', () => {
    expect(pendingCountLabel({ items: [], next_cursor: null })).toBe('0')
    expect(pendingCountLabel({ items: new Array(100), next_cursor: 'abc' })).toBe('100+')
  })
})

describe('điều hướng (trang đã có đến Group 6)', () => {
  it('engineer và reviewer thấy Trang chủ, Tài khoản; admin thấy thêm trang quản trị', () => {
    for (const name of ['engineer', 'reviewer']) {
      expect(visibleNav(mockMe(name)).map((i) => i.path)).toEqual(['/home', '/account'])
    }
    expect(visibleNav(mockMe('admin')).map((i) => i.path)).toEqual([
      '/home',
      '/admin/users',
      '/account',
    ])
  })
})

describe('lỗi khi tải /auth/me', () => {
  function renderWithMeError(status: number) {
    // Không tải lại khi mount: giữ nguyên trạng thái lỗi để kiểm tra phần hiển thị.
    const client = new QueryClient({ defaultOptions: { queries: { retryOnMount: false } } })
    const query = client.getQueryCache().build(client, { queryKey: ME_QUERY_KEY })
    query.setState({ status: 'error', error: new ApiError(status, 'unknown', 'x') })
    return renderToStaticMarkup(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <RequirePermission requirement="authenticated">nội dung</RequirePermission>
        </MemoryRouter>
      </QueryClientProvider>,
    )
  }

  it('lỗi khác 401 hiện thông báo và nút thử lại (không phải màn hình trắng)', () => {
    const html = renderWithMeError(500)
    expect(html).toContain('Không tải được dữ liệu')
    expect(html).toContain('Thử lại')
  })

  it('401 không hiện gì (đã chuyển về /login ở tầng toàn cục)', () => {
    expect(renderWithMeError(401)).toBe('')
  })
})
