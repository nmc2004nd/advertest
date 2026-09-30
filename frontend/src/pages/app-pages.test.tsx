import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'

import { listMocks, mockMe } from '@/api/mocks'
import { ApiError } from '@/api/errors'
import { RequirePermission } from '@/auth/RequirePermission'
import { PENDING_USERS_QUERY_KEY, pendingCountLabel } from '@/auth/pending-count'
import { ME_QUERY_KEY } from '@/auth/useMe'
import type { UserAdminPage } from '@/contracts/schemas'
import { visibleNav } from '@/nav/config'
import type { ExperimentPage } from '@/contracts/api'
import { EXPERIMENTS_KEY } from '@/features/experiments/api'
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

  it('engineer thấy khối experiment (Phase 5); reviewer vẫn "Sắp có"; không thấy khối admin', () => {
    const mine = listMocks<ExperimentPage>('experiment_page').find((p) => p.items.length > 0)
    const html = render(<HomePage />, '/home', 'engineer_reviewer', [
      [[...EXPERIMENTS_KEY, 'mine-recent'], mine],
    ])
    expect(html.match(/Sắp có/g)).toHaveLength(1)
    expect(html).toContain('href="/experiments/new"')
    expect(html).toContain('Đang chạy hoặc chờ')
    expect(html).toContain('Kết thúc gần đây')
    expect(html).toContain('role="progressbar"')
    expect(html).not.toContain('chờ duyệt')
  })

  it('nhãn đếm có dấu + khi còn trang sau', () => {
    expect(pendingCountLabel({ items: [], next_cursor: null })).toBe('0')
    expect(pendingCountLabel({ items: new Array(100), next_cursor: 'abc' })).toBe('100+')
  })
})

describe('điều hướng (Phase 5 Group 6: bật Experiment và Tạo experiment)', () => {
  it('engineer có Tạo experiment; reviewer không; admin thêm trang quản trị', () => {
    expect(visibleNav(mockMe('engineer')).map((i) => i.path)).toEqual([
      '/home',
      '/experiments',
      '/experiments/new',
      '/account',
    ])
    expect(visibleNav(mockMe('reviewer')).map((i) => i.path)).toEqual([
      '/home',
      '/experiments',
      '/account',
    ])
    expect(visibleNav(mockMe('admin')).map((i) => i.path)).toEqual([
      '/home',
      '/experiments',
      '/admin/users',
      '/admin/audit',
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
