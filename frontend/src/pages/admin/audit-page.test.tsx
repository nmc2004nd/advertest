import { describe, expect, it } from 'vitest'

import { auditParams, EMPTY_FILTERS } from '@/admin/useAudit'
import { listMocks } from '@/api/mocks'
import type { AuditLogPage } from '@/contracts/schemas'
import { expectLabelledControls, render } from '@/test-utils'

import { AuditPage } from './AuditPage'

const page = listMocks<AuditLogPage>('audit_log_page')[0]

describe('auditParams', () => {
  it('chỉ gửi bộ lọc có giá trị, ngày chuyển sang UTC, kèm cursor', () => {
    expect(auditParams(EMPTY_FILTERS, null).toString()).toBe('limit=50')
    const params = auditParams(
      { ...EMPTY_FILTERS, actorId: 'abc', action: 'user.approved', from: '2026-09-01' },
      'cur',
    )
    expect(params.get('actor_id')).toBe('abc')
    expect(params.get('action')).toBe('user.approved')
    expect(params.get('since')).toMatch(/Z$/)
    expect(params.has('until')).toBe(false)
    expect(params.get('cursor')).toBe('cur')
  })
})

describe('/admin/audit', () => {
  const html = render(<AuditPage />, '/admin/audit', 'admin', [
    [['audit', EMPTY_FILTERS], { pages: [page], pageParams: [null] }],
  ])

  it('bộ lọc có 5 ô có nhãn', () => {
    expectLabelledControls(html, 5)
  })

  it('bảng từ 1280px, thẻ dưới 1280px; actor hệ thống hiển thị "Hệ thống"', () => {
    expect(html).toMatch(/class="hidden [^"]*xl:block"><table/)
    expect(html).toMatch(/<ul class="[^"]*xl:hidden"/)
    expect(html).toContain('Hệ thống')
    expect(html).toContain('Duyệt tài khoản')
  })

  it('ID dài rút gọn ở giữa, kèm nút copy', () => {
    const id = page.items[0].id
    expect(html).toContain(`${id.slice(0, 8)}…${id.slice(-4)}`)
    expect(html).toContain('aria-label="Copy"')
  })
})
