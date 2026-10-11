import { useQuery } from '@tanstack/react-query'

import { apiGet } from '@/api/client'
import { PENDING_COUNT_LIMIT, PENDING_USERS_QUERY_KEY } from '@/auth/pending-count'
import { can } from '@/auth/permissions'
import type {
  AttackSpecAdminPage,
  AttackSpecAdminView,
  ExperimentPage,
  ModelSummary,
  ReviewQueueItem,
} from '@/contracts/api'
import type { Me, UserAdminPage } from '@/contracts/schemas'
import { EXPERIMENTS_KEY } from '@/features/experiments/api'
import { useReviewQueue } from '@/features/reviews/api'

import { collectTodos, type TodoItem } from './todos'

export const TODO_EXPERIMENTS_KEY = [...EXPERIMENTS_KEY, 'todo'] as const
export const PENDING_SPECS_KEY = ['attack-specs', 'pending'] as const
export const TODO_ADMIN_SPECS_KEY = ['admin', 'attack-specs', 'todo'] as const
export const MODELS_KEY = ['models'] as const

const MINE_LIMIT = 100

/** Mọi trang của `GET /admin/attack-specs` (catalog nhỏ, vài chục spec). */
async function allAdminSpecs(): Promise<AttackSpecAdminView[]> {
  const items: AttackSpecAdminView[] = []
  let cursor: string | null = null
  do {
    const params = new URLSearchParams({ limit: '100' })
    if (cursor) params.set('cursor', cursor)
    const page: AttackSpecAdminPage = await apiGet<AttackSpecAdminPage>(
      `/admin/attack-specs?${params}`,
    )
    items.push(...page.items)
    cursor = page.next_cursor
  } while (cursor)
  return items
}

/** Experiment của tôi cần xử lý: `completed` và `changes_requested`. */
async function myTodoExperiments(): Promise<ExperimentPage['items']> {
  const pages = await Promise.all(
    (['completed', 'changes_requested'] as const).map((status) =>
      apiGet<ExperimentPage>(`/experiments?owner=me&status=${status}&limit=${MINE_LIMIT}`),
    ),
  )
  return pages.flatMap((p) => p.items)
}

/**
 * Lấy dữ liệu cho danh sách việc cần làm từ các endpoint hiện có, chỉ gọi endpoint ứng với vai trò
 * và quyền của người dùng (requirements.md Phase R3, mục Trang chủ).
 */
export function useTodos(me: Me | undefined): {
  todos: TodoItem[]
  loading: boolean
  failed: boolean
} {
  const roles = me?.roles ?? []
  const engineer = roles.includes('engineer') && can(me, 'experiment.read')
  const reviewer = roles.includes('reviewer') && can(me, 'review.decide')
  const approver = roles.includes('reviewer') && can(me, 'attack_catalog.approve')
  const admin = roles.includes('admin')
  const users = admin && can(me, 'user.manage')
  const catalog = admin && can(me, 'attack_catalog.manage')
  const models = admin && can(me, 'model.manage')

  const queries = {
    experiments: useQuery({
      enabled: engineer,
      queryKey: TODO_EXPERIMENTS_KEY,
      queryFn: myTodoExperiments,
    }),
    waiting: useReviewQueue('waiting', 'submitted_at', reviewer),
    mine: useReviewQueue('mine', 'submitted_at', reviewer),
    pendingSpecs: useQuery({
      enabled: approver,
      queryKey: PENDING_SPECS_KEY,
      queryFn: () => apiGet<AttackSpecAdminView[]>('/attack-specs/pending'),
    }),
    users: useQuery({
      enabled: users,
      queryKey: PENDING_USERS_QUERY_KEY,
      queryFn: () =>
        apiGet<UserAdminPage>(`/admin/users?status=pending&limit=${PENDING_COUNT_LIMIT}`),
    }),
    adminSpecs: useQuery({
      enabled: catalog,
      queryKey: TODO_ADMIN_SPECS_KEY,
      queryFn: allAdminSpecs,
    }),
    models: useQuery({
      enabled: models,
      queryKey: MODELS_KEY,
      queryFn: () => apiGet<ModelSummary[]>('/models'),
    }),
  }
  const enabled = {
    experiments: engineer,
    waiting: reviewer,
    mine: reviewer,
    pendingSpecs: approver,
    users,
    adminSpecs: catalog,
    models,
  }
  const active = (Object.keys(queries) as (keyof typeof queries)[]).filter((k) => enabled[k])
  const loading = active.some((k) => queries[k].isPending)
  const failed = active.some((k) => queries[k].isError)
  const reviews: ReviewQueueItem[] = [...(queries.waiting.data ?? []), ...(queries.mine.data ?? [])]
  const todos = me
    ? collectTodos(me, {
        myExperiments: queries.experiments.data,
        reviews,
        pendingSpecs: queries.pendingSpecs.data,
        protocolDrafts: 0,
        pendingUsers: queries.users.data && {
          count: queries.users.data.items.length,
          more: queries.users.data.next_cursor !== null,
        },
        adminSpecs: queries.adminSpecs.data,
        models: queries.models.data,
      })
    : []
  return { todos, loading, failed }
}
