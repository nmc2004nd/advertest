import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'

import { mockMe } from '@/api/mocks'
import { ForbiddenPage } from '@/pages/ForbiddenPage'

import { RequirePermission } from './RequirePermission'
import { ME_QUERY_KEY } from './useMe'

function render(node: ReactNode, me?: string): string {
  const client = new QueryClient()
  if (me) client.setQueryData(ME_QUERY_KEY, mockMe(me))
  return renderToStaticMarkup(
    <QueryClientProvider client={client}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('RequirePermission', () => {
  it('hiện nội dung khi có quyền', () => {
    const html = render(
      <RequirePermission requirement="user.manage">bí mật</RequirePermission>,
      'admin',
    )
    expect(html).toContain('bí mật')
  })

  it('không hiện nội dung khi thiếu quyền', () => {
    const html = render(
      <RequirePermission requirement="user.manage">bí mật</RequirePermission>,
      'engineer',
    )
    expect(html).not.toContain('bí mật')
  })

  it('đang tải thì hiện trạng thái chờ', () => {
    const html = render(<RequirePermission requirement="authenticated">bí mật</RequirePermission>)
    expect(html).toContain('Đang tải')
    expect(html).not.toContain('bí mật')
  })
})

describe('ForbiddenPage', () => {
  it('có thông báo và nút về trang chủ', () => {
    const html = render(<ForbiddenPage />)
    expect(html).toContain('Không có quyền truy cập')
    expect(html).toContain('href="/home"')
  })
})
