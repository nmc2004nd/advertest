import type {
  AttackSpecAdminView,
  ExperimentSummary,
  ModelSummary,
  ReviewQueueItem,
} from '@/contracts/api'
import type { Role } from '@/contracts/schemas'

/**
 * Việc cần làm trên /home theo vai trò (requirements.md Phase R3, mục Trang chủ). Hàm thuần: nhận dữ
 * liệu từ các endpoint hiện có, trả danh sách việc có số lượng và link tới đúng nơi xử lý. Người có
 * nhiều vai trò thấy gộp; mỗi loại việc xuất hiện một lần.
 */
export type TodoKind =
  | 'submit_ready'
  | 'changes_requested'
  | 'promote_ready'
  | 'review_pending'
  | 'spec_pending'
  | 'protocol_draft'
  | 'user_pending'
  | 'spec_check_failed'
  | 'model_check_failed'

export interface TodoLink {
  to: string
  label: string
}

export interface TodoItem {
  kind: TodoKind
  count: number
  /** Số hiện trên giao diện; "100+" khi còn trang sau. */
  countLabel: string
  title: string
  /** Nơi xử lý: chỉ một đối tượng thì tới thẳng đối tượng đó. */
  to: string
  /** Tối đa `TODO_LINKS` đối tượng cụ thể. */
  links: TodoLink[]
}

export const TODO_LINKS = 3

export const TODO_KINDS_BY_ROLE: Record<Role, TodoKind[]> = {
  engineer: ['submit_ready', 'changes_requested', 'promote_ready'],
  reviewer: ['review_pending', 'spec_pending', 'protocol_draft'],
  admin: ['user_pending', 'spec_check_failed', 'model_check_failed'],
}

export interface TodoSources {
  /** Experiment của tôi ở trạng thái `completed` hoặc `changes_requested`. */
  myExperiments?: ExperimentSummary[]
  /** `GET /reviews?status=waiting` và `mine` (backend đã bỏ experiment do tôi tạo). */
  reviews?: ReviewQueueItem[]
  /** `GET /attack-specs/pending`. */
  pendingSpecs?: AttackSpecAdminView[]
  /** Protocol nháp của tôi. Contract chưa có protocol `draft` nên hiện luôn là 0 (người duyệt chốt
   * 2026-10-11: giữ loại việc, chưa có nguồn). */
  protocolDrafts?: number
  /** Trang đầu của `GET /admin/users?status=pending`. */
  pendingUsers?: { count: number; more: boolean }
  /** `GET /admin/attack-specs` (mọi trang). */
  adminSpecs?: AttackSpecAdminView[]
  /** `GET /models`. */
  models?: ModelSummary[]
}

interface Me {
  id: string
  roles: readonly Role[]
}

function item(
  kind: TodoKind,
  title: string,
  listTo: string,
  targets: TodoLink[],
  count = targets.length,
  more = false,
): TodoItem | null {
  if (count === 0) return null
  return {
    kind,
    count,
    countLabel: `${count}${more ? '+' : ''}`,
    title,
    to: count === 1 && targets.length === 1 ? targets[0].to : listTo,
    links: targets.slice(0, TODO_LINKS),
  }
}

const experimentLink = (e: { id: string; name: string }, tab = ''): TodoLink => ({
  to: `/experiments/${e.id}${tab ? `?tab=${tab}` : ''}`,
  label: e.name,
})

function uniqueById<T>(items: T[], id: (x: T) => string): T[] {
  const seen = new Set<string>()
  return items.filter((x) => {
    const key = id(x)
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

function build(kind: TodoKind, me: Me, s: TodoSources): TodoItem | null {
  const mine = uniqueById(
    (s.myExperiments ?? []).filter((e) => e.owner.id === me.id),
    (e) => e.id,
  )
  switch (kind) {
    case 'submit_ready':
      return item(
        kind,
        'Experiment đã xong, chưa gửi duyệt',
        '/experiments?owner=me&status=completed',
        mine
          .filter((e) => e.status === 'completed' && e.mode === 'official')
          .map((e) => experimentLink(e)),
      )
    case 'changes_requested':
      return item(
        kind,
        'Experiment bị yêu cầu sửa',
        '/experiments?owner=me&status=changes_requested',
        mine
          .filter((e) => e.status === 'changes_requested')
          .map((e) => experimentLink(e, 'review')),
      )
    case 'promote_ready':
      return item(
        kind,
        'Experiment Khám phá đã xong, có thể nâng lên chính thức',
        '/experiments?owner=me&status=completed',
        mine
          .filter((e) => e.status === 'completed' && e.mode === 'exploration')
          .map((e) => experimentLink(e)),
      )
    case 'review_pending':
      return item(
        kind,
        'Review đang chờ',
        '/reviews?status=waiting',
        uniqueById(s.reviews ?? [], (r) => r.experiment.id)
          .filter((r) => r.decision === null && r.experiment.owner.id !== me.id)
          .map((r) => ({ to: `/reviews/${r.experiment.id}`, label: r.experiment.name })),
      )
    case 'spec_pending':
      return item(
        kind,
        'Attack spec chờ kích hoạt',
        '/attack-specs/pending',
        uniqueById(s.pendingSpecs ?? [], (spec) => spec.id)
          .filter((spec) => spec.status === 'pending_approval' && spec.created_by?.id !== me.id)
          .map((spec) => ({ to: '/attack-specs/pending', label: `${spec.name} v${spec.version}` })),
      )
    case 'protocol_draft':
      return item(kind, 'Protocol nháp của bạn', '/protocols', [], s.protocolDrafts ?? 0)
    case 'user_pending':
      return item(
        kind,
        'Tài khoản chờ duyệt',
        '/admin/users',
        [],
        s.pendingUsers?.count ?? 0,
        s.pendingUsers?.more ?? false,
      )
    case 'spec_check_failed':
      return item(
        kind,
        'Attack spec kiểm tra không đạt',
        '/admin/attacks',
        uniqueById(s.adminSpecs ?? [], (spec) => spec.id)
          .filter((spec) => spec.status === 'check_failed')
          .map((spec) => ({ to: '/admin/attacks', label: `${spec.name} v${spec.version}` })),
      )
    case 'model_check_failed':
      return item(
        kind,
        'Model kiểm tra không đạt',
        '/admin/models',
        uniqueById(s.models ?? [], (m) => m.id)
          .filter((m) => m.status === 'check_failed')
          .map((m) => ({ to: '/admin/models', label: m.name })),
      )
  }
}

export function collectTodos(me: Me, sources: TodoSources): TodoItem[] {
  const kinds = new Set(me.roles.flatMap((role) => TODO_KINDS_BY_ROLE[role]))
  return [...kinds].flatMap((kind) => build(kind, me, sources) ?? [])
}
