// Tiện ích cho test Vitest (môi trường node, render bằng react-dom/server). Không dùng trong app.
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router'
import { expect } from 'vitest'

import { mockMe } from '@/api/mocks'
import { ME_QUERY_KEY } from '@/auth/useMe'

/** Render tĩnh trong router bộ nhớ; `me` là tên mock `contracts/mocks/me/<tên>.json`. */
export function render(
  node: ReactNode,
  path = '/',
  me?: string,
  data: [readonly unknown[], unknown][] = [],
): string {
  const client = new QueryClient()
  if (me) client.setQueryData(ME_QUERY_KEY, mockMe(me))
  for (const [key, value] of data) client.setQueryData(key, value)
  return renderToStaticMarkup(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>{node}</MemoryRouter>
    </QueryClientProvider>,
  )
}

/** Mọi ô nhập có nhãn gắn đúng id và font 16px (requirements.md Phase 4, Hành vi chung). */
export function expectLabelledControls(html: string, count: number): void {
  const ids = [...html.matchAll(/<(?:input|select|textarea)[^>]*\sid="([^"]+)"/g)].map((m) => m[1])
  expect(ids).toHaveLength(count)
  for (const id of ids) expect(html).toContain(`for="${id}"`)
  expect(html.match(/<(?:input|select|textarea)[^>]*text-base/g)).toHaveLength(count)
}
