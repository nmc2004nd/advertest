// Phase R3 Group 7: thử nhanh (validation.md Group 7).
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '@/api/errors'
import { listMocks, mockMe, modelMocks } from '@/api/mocks'
import { ME_QUERY_KEY } from '@/auth/useMe'
import type { AttackSpecView, ExperimentPreset, QuickTryView } from '@/contracts/api'
import { render } from '@/test-utils'

import { CreateError, QuickTryPage, QuickTryResult, QuickTryStatus } from './QuickTryPage'

const specs = listMocks<AttackSpecView>('attack_spec')
const presets = listMocks<ExperimentPreset>('experiment_preset')
const views = listMocks<QuickTryView>('quick_try_view')
const completed = views.find((v) => v.status === 'completed')
if (!completed) throw new Error('Thiếu mock quick_try_view completed')

const data: [readonly unknown[], unknown][] = [
  [['models'], modelMocks()],
  [['attack-specs'], specs],
  [['experiment-presets'], presets],
]

afterEach(() => {
  vi.unstubAllGlobals()
})

/** Render với query `['quick-tries', id]` ở trạng thái lỗi (không tải lại khi mount). */
function renderWithError(node: ReactNode, id: string, error: ApiError): string {
  const client = new QueryClient({ defaultOptions: { queries: { retryOnMount: false } } })
  client.setQueryData(ME_QUERY_KEY, mockMe('engineer'))
  const query = client.getQueryCache().build(client, { queryKey: ['quick-tries', id] })
  query.setState({ status: 'error', error })
  return renderToStaticMarkup(
    <QueryClientProvider client={client}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('/quick-try: form', () => {
  it('ô chọn Model, Attack, radiogroup Preset, ô file Ảnh và nút Chạy thử nhanh', () => {
    const html = render(<QuickTryPage />, '/quick-try', 'engineer', data)
    for (const label of ['Model', 'Attack', 'Ảnh']) expect(html).toContain(`>${label}</label>`)
    expect(html).toContain('role="radiogroup" aria-label="Preset"')
    expect(html).toContain('accept="image/jpeg,image/png"')
    expect(html).toMatch(/<button[^>]*type="submit"[^>]*>Chạy thử nhanh<\/button>/)
  })

  it('danh sách attack không có patch', () => {
    const patch = specs.find((s) => s.requires_training)
    if (!patch) throw new Error('Thiếu mock spec patch')
    const html = render(<QuickTryPage />, '/quick-try', 'engineer', data)
    expect(html).not.toContain(`(${patch.name})</option>`)
  })

  it('gợi ý attack dùng Term cho patch và attack white-box (M4)', () => {
    const html = render(<QuickTryPage />, '/quick-try', 'engineer', data)
    expect(html).toContain('data-term="patch"')
    expect(html).toContain('data-term="white_box"')
  })

  it('chỉ liệt kê model ready', () => {
    const ready = modelMocks().find((m) => m.status === 'ready')
    if (!ready) throw new Error('Thiếu mock model ready')
    const failed = { ...ready, id: '00000000-0000-4000-8000-000000000001', status: 'check_failed' }
    const html = render(<QuickTryPage />, '/quick-try', 'engineer', [
      ...data,
      [['models'], [ready, failed]],
    ])
    expect(html).toContain(`value="${ready.id}"`)
    expect(html).not.toContain(`value="${failed.id}"`)
  })
})

describe('kết quả', () => {
  it('nhãn "Không phải kết quả kiểm thử" ở đầu kết quả, kèm giờ xóa HH:MM', () => {
    const html = render(<QuickTryResult view={completed} />, '/quick-try', 'engineer', data)
    const label = html.indexOf('data-testid="not-a-test-result"')
    expect(label).toBeGreaterThan(0)
    expect(label).toBeLessThan(html.indexOf('data-testid="attacked-image"'))
    expect(html).toContain('Không phải kết quả kiểm thử')
    expect(html).toMatch(/Ảnh tự xóa sau 24 giờ, lúc \d{2}:\d{2}/)
  })

  it('thanh trượt Level, ảnh sạch và ảnh tấn công cạnh nhau, bảng object và số đếm', () => {
    const html = render(<QuickTryResult view={completed} />, '/quick-try', 'engineer', data)
    expect(html).toMatch(/<input[^>]*type="range"[^>]*aria-label="Level"/)
    // M4: nhãn Level là Term (lần đầu thuật ngữ xuất hiện trong kết quả).
    expect(html).toMatch(/data-term="level"[^>]*>Level</)
    expect(html).toContain(`max="${completed.levels.length - 1}"`)
    expect(html).toContain(`src="${completed.clean_image_url ?? ''}"`)
    expect(html).toContain(`src="${completed.levels[0].image_url}"`)
    expect(html).toContain('data-testid="object-table"')
    expect(html).toContain('data-count="kept"')
    expect(html).toContain('md:grid-cols-2')
  })

  it('đổi level chỉ đổi dữ liệu đã tải: ảnh tấn công và bảng theo level', () => {
    const last = completed.levels.length - 1
    const first = render(<QuickTryResult view={completed} />, '/quick-try', 'engineer', data)
    const other = render(
      <QuickTryResult view={completed} initialIndex={last} />,
      '/quick-try',
      'engineer',
      data,
    )
    expect(other).toContain(`src="${completed.levels[last].image_url}"`)
    expect(other).not.toContain(`src="${completed.levels[0].image_url}"`)
    const rows = (html: string) => html.split('data-kind="quick_try_object"').length
    expect(rows(other)).not.toBe(rows(first))
  })
})

describe('lỗi', () => {
  const busy = new ApiError(429, 'quick_try_busy', 'x')

  it('429: link tới lượt đang chạy (id nhớ ở trình duyệt)', () => {
    const me = mockMe('engineer')
    vi.stubGlobal('localStorage', {
      getItem: (key: string) => (key === `advertest-quick-try:${me.id}` ? completed.id : null),
    })
    const html = render(<CreateError error={busy} userId={me.id} />)
    expect(html).toContain('Bạn đang có một lượt thử chưa xong')
    expect(html).toContain(`href="/quick-try?id=${completed.id}"`)
  })

  it('429 không có id đã nhớ: chỉ thông báo, không link', () => {
    const html = render(<CreateError error={busy} userId="x" />)
    expect(html).toContain('Bạn đang có một lượt thử chưa xong')
    expect(html).not.toContain('href=')
  })

  it('410: "Lượt thử đã hết hạn và bị xóa" kèm nút Thử lại', () => {
    const html = renderWithError(
      <QuickTryStatus id={completed.id} onReset={() => undefined} />,
      completed.id,
      new ApiError(410, 'gone', 'x'),
    )
    expect(html).toContain('Lượt thử đã hết hạn và bị xóa')
    expect(html).toMatch(/<button[^>]*>Thử lại<\/button>/)
  })

  it('đang chạy: badge trạng thái, chưa có kết quả', () => {
    const queued = views.find((v) => v.status === 'queued')
    if (!queued) throw new Error('Thiếu mock queued')
    const html = render(
      <QuickTryStatus id={queued.id} onReset={() => undefined} />,
      '/quick-try',
      'engineer',
      [[['quick-tries', queued.id], queued]],
    )
    expect(html).toContain('data-status="queued"')
    expect(html).not.toContain('data-testid="quick-try-result"')
  })
})
