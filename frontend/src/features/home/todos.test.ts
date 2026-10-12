import { describe, expect, it } from 'vitest'

import type {
  AttackSpecAdminView,
  ExperimentSummary,
  ModelSummary,
  ReviewQueueItem,
} from '@/contracts/api'
import type { Role } from '@/contracts/schemas'

import { collectTodos, type TodoKind, type TodoSources } from './todos'

const ME = 'me'
const OTHER = 'other'

// Chỉ các trường mà hàm gom việc đọc.
const exp = (id: string, status: string, mode: string, owner = ME) =>
  ({ id, name: `exp-${id}`, status, mode, owner: { id: owner } }) as unknown as ExperimentSummary
const review = (id: string, decision: string | null = null, owner = OTHER) =>
  ({ experiment: exp(id, 'in_review', 'official', owner), decision }) as unknown as ReviewQueueItem
const spec = (id: string, status: string, createdBy: string | null = OTHER) =>
  ({
    id,
    name: `spec-${id}`,
    version: 1,
    status,
    created_by: createdBy ? { id: createdBy } : null,
  }) as unknown as AttackSpecAdminView
const model = (id: string, status: string) =>
  ({ id, name: `model-${id}`, status }) as unknown as ModelSummary

const FULL: TodoSources = {
  myExperiments: [
    exp('o1', 'completed', 'official'),
    exp('o2', 'completed', 'official'),
    exp('x1', 'completed', 'exploration'),
    exp('c1', 'changes_requested', 'official'),
    exp('n1', 'completed', 'official', OTHER), // của người khác: không tính
  ],
  reviews: [
    review('r1'),
    review('r2'),
    review('r1'),
    review('d1', 'approve'),
    review('m1', null, ME),
  ],
  pendingSpecs: [spec('s1', 'pending_approval'), spec('s2', 'pending_approval', ME)],
  protocolDrafts: 0,
  pendingUsers: { count: 100, more: true },
  adminSpecs: [spec('a1', 'check_failed', null), spec('a2', 'active'), spec('a3', 'check_failed')],
  models: [model('m1', 'check_failed'), model('m2', 'ready')],
}

const counts = (roles: Role[], sources: TodoSources = FULL) =>
  Object.fromEntries(
    collectTodos({ id: ME, roles }, sources).map((t) => [t.kind, t.countLabel]),
  ) as Partial<Record<TodoKind, string>>

describe('việc cần làm theo vai trò (requirements.md Phase R3, mục Trang chủ)', () => {
  it('engineer: đã xong chưa gửi duyệt, bị yêu cầu sửa, Khám phá có thể nâng lên chính thức', () => {
    expect(counts(['engineer'])).toEqual({
      submit_ready: '2',
      changes_requested: '1',
      promote_ready: '1',
    })
  })

  it('reviewer: review đang chờ (không trùng, bỏ đã quyết định và của mình), spec chờ của người khác', () => {
    // protocol_draft = 0 nên không hiện.
    expect(counts(['reviewer'])).toEqual({ review_pending: '2', spec_pending: '1' })
  })

  it('admin: tài khoản chờ duyệt (có trang sau thì "+"), spec và model kiểm tra không đạt', () => {
    expect(counts(['admin'])).toEqual({
      user_pending: '100+',
      spec_check_failed: '2',
      model_check_failed: '1',
    })
  })

  it('nhiều vai trò: gộp, mỗi loại việc một lần, theo thứ tự vai trò', () => {
    const todos = collectTodos({ id: ME, roles: ['reviewer', 'engineer', 'reviewer'] }, FULL)
    expect(todos.map((t) => t.kind)).toEqual([
      'review_pending',
      'spec_pending',
      'submit_ready',
      'changes_requested',
      'promote_ready',
    ])
  })

  it('không có việc: danh sách rỗng', () => {
    expect(collectTodos({ id: ME, roles: ['engineer', 'reviewer', 'admin'] }, {})).toEqual([])
    expect(collectTodos({ id: ME, roles: [] }, FULL)).toEqual([])
  })

  it('protocol nháp: hiện khi nguồn có số lượng', () => {
    expect(counts(['reviewer'], { protocolDrafts: 2 })).toEqual({ protocol_draft: '2' })
  })
})

describe('link của việc cần làm', () => {
  const todo = (kind: TodoKind, roles: Role[], sources: TodoSources = FULL) => {
    const found = collectTodos({ id: ME, roles }, sources).find((t) => t.kind === kind)
    if (!found) throw new Error(`Thiếu việc ${kind}`)
    return found
  }

  it('một đối tượng: link thẳng tới đối tượng đó', () => {
    expect(todo('promote_ready', ['engineer']).to).toBe('/experiments/x1')
    expect(todo('changes_requested', ['engineer']).to).toBe('/experiments/c1?tab=review')
  })

  it('nhiều đối tượng: link tới danh sách đã lọc, kèm tối đa 3 đối tượng', () => {
    const ready = todo('submit_ready', ['engineer'])
    expect(ready.to).toBe('/experiments?owner=me&status=completed')
    expect(ready.links.map((l) => l.to)).toEqual(['/experiments/o1', '/experiments/o2'])
    const many = todo('submit_ready', ['engineer'], {
      myExperiments: ['1', '2', '3', '4'].map((id) => exp(id, 'completed', 'official')),
    })
    expect(many.count).toBe(4)
    expect(many.links).toHaveLength(3)
  })

  it('review và việc của admin tới đúng trang xử lý', () => {
    expect(todo('review_pending', ['reviewer']).to).toBe('/reviews?status=waiting')
    expect(todo('user_pending', ['admin']).to).toBe('/admin/users')
    expect(todo('model_check_failed', ['admin']).to).toBe('/models')
  })
})
