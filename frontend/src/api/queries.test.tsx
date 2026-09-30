import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import { useRun } from './queries'

function Probe({ runId }: { runId: string }) {
  useRun(runId)
  return null
}

function queryFor(runId: string) {
  const client = new QueryClient()
  renderToStaticMarkup(
    <QueryClientProvider client={client}>
      <Probe runId={runId} />
    </QueryClientProvider>,
  )
  const query = client.getQueryCache().find({ queryKey: ['runs', runId] })
  return (query?.options as { enabled?: unknown } | undefined)?.enabled
}

describe('useRun', () => {
  it('id rỗng thì không gọi API (review Group 6 #1: trình xem mở không có ?run=)', () => {
    expect(queryFor('')).toBe(false)
  })

  it('có id thì gọi', () => {
    expect(queryFor('abc')).toBe(true)
  })
})
