/**
 * Luồng chính của MVP (docs/demo-mvp.md): admin duyệt tài khoản → reviewer chốt protocol →
 * engineer cấu hình experiment → worker chạy attack → engineer gửi duyệt → reviewer quyết định →
 * report chính thức và xác minh. File này chỉ tính toán (không gọi API) để test được.
 */
import { can, type Requirement } from '@/auth/permissions'
import type { ExperimentStatus, ExperimentSummary, Me, Role } from '@/contracts/api'

export type StageId = 'accounts' | 'protocol' | 'configure' | 'run' | 'submit' | 'review' | 'report'

/** `action`: có việc chờ chính người dùng này; `active`: có việc đang diễn ra; `idle`: chưa có gì. */
export type StageState = 'action' | 'active' | 'idle'

export interface StageDef {
  id: StageId
  title: string
  owner: Role | 'worker'
  /** Permission để làm việc của bước (hiện nút CTA). */
  act: Requirement
}

export const STAGES: readonly StageDef[] = [
  { id: 'accounts', title: 'Duyệt tài khoản', owner: 'admin', act: 'user.manage' },
  { id: 'protocol', title: 'Chốt protocol', owner: 'reviewer', act: 'protocol.manage' },
  { id: 'configure', title: 'Cấu hình experiment', owner: 'engineer', act: 'experiment.create' },
  { id: 'run', title: 'Chạy attack', owner: 'worker', act: 'experiment.read' },
  { id: 'submit', title: 'Gửi duyệt', owner: 'engineer', act: 'experiment.submit_review' },
  { id: 'review', title: 'Review và quyết định', owner: 'reviewer', act: 'review.decide' },
  { id: 'report', title: 'Report và xác minh', owner: 'reviewer', act: 'report.read' },
]

export const OWNER_LABEL: Record<StageDef['owner'], string> = {
  admin: 'Quản trị viên',
  reviewer: 'Reviewer',
  engineer: 'Kỹ sư',
  worker: 'Worker',
}

/** Số liệu đầu vào; `null` = người dùng không có quyền xem hoặc chưa tải xong. */
export interface FlowData {
  pendingUsers: number | null
  activeProtocols: number | null
  experiments: ExperimentSummary[] | null
  waitingReviews: number | null
  myReviews: number | null
  readyReports: number | null
}

export interface StageView extends StageDef {
  state: StageState
  /** Một câu mô tả tình trạng hiện tại của bước. */
  status: string
  /** Nút hành động (chỉ khi người dùng có quyền làm việc của bước). */
  cta: { label: string; to: string } | null
}

const count = (items: ExperimentSummary[], statuses: readonly ExperimentStatus[]) =>
  items.filter((e) => statuses.includes(e.status))

const REVIEWING: readonly ExperimentStatus[] = ['submitted_for_review', 'in_review']

export function buildStages(me: Pick<Me, 'id' | 'roles'>, data: FlowData): StageView[] {
  const exps = data.experiments ?? []
  const mine = exps.filter((e) => e.owner.id === me.id)
  return STAGES.map((stage): StageView => {
    const allowed = can(me, stage.act)
    const base = { ...stage, cta: null as StageView['cta'] }
    switch (stage.id) {
      case 'accounts': {
        const n = data.pendingUsers
        if (n === null)
          return { ...base, state: 'idle', status: 'Quản trị viên duyệt và gán vai trò' }
        return {
          ...base,
          state: n > 0 ? 'action' : 'idle',
          status:
            n > 0 ? `${n} người đang chờ được vào hệ thống` : 'Không có ai đang chờ được duyệt',
          cta: allowed
            ? { label: n > 0 ? 'Duyệt ngay' : 'Mở danh sách', to: '/admin/users' }
            : null,
        }
      }
      case 'protocol': {
        const n = data.activeProtocols
        const status =
          n === null
            ? 'Reviewer chốt tiêu chí đạt'
            : n > 0
              ? `${n} protocol đang dùng`
              : 'Chưa có protocol'
        return {
          ...base,
          state: n === 0 && allowed ? 'action' : n ? 'active' : 'idle',
          status,
          cta: allowed
            ? n === 0
              ? { label: 'Tạo protocol', to: '/protocols?new=1' }
              : { label: 'Xem protocol', to: '/protocols' }
            : null,
        }
      }
      case 'configure': {
        const drafts = count(mine, ['draft']).length
        return {
          ...base,
          state: allowed && mine.length === 0 ? 'action' : 'idle',
          status:
            drafts > 0
              ? `${drafts} bản nháp chưa chạy`
              : mine.length > 0
                ? `Bạn đã tạo ${mine.length} experiment`
                : allowed
                  ? 'Chọn model, slice và attack trong 6 bước'
                  : 'Kỹ sư chọn model, slice và attack',
          cta: allowed ? { label: 'Tạo experiment', to: '/experiments/new' } : null,
        }
      }
      case 'run': {
        const running = count(exps, ['running']).length
        const queued = count(exps, ['queued']).length
        const parts = [running && `${running} đang chạy`, queued && `${queued} đang chờ`].filter(
          Boolean,
        )
        return {
          ...base,
          state: running + queued > 0 ? 'active' : 'idle',
          status: parts.length ? parts.join(', ') : 'Không có experiment nào đang chạy',
          cta:
            running + queued > 0
              ? { label: 'Theo dõi tiến độ', to: '/experiments?status=running' }
              : null,
        }
      }
      case 'submit': {
        const ready = count(mine, ['completed'])
        const back = count(mine, ['changes_requested'])
        if (!allowed) {
          const n = count(exps, ['completed']).length
          return {
            ...base,
            state: 'idle',
            status: n ? `${n} experiment xong, chưa gửi duyệt` : 'Kỹ sư gửi kết quả đi duyệt',
          }
        }
        const first = back[0] ?? ready[0]
        return {
          ...base,
          state: ready.length + back.length > 0 ? 'action' : 'idle',
          status: back.length
            ? `${back.length} experiment được yêu cầu sửa`
            : ready.length
              ? `${ready.length} experiment xong, chờ bạn gửi duyệt`
              : 'Chưa có kết quả nào chờ gửi',
          cta: first
            ? {
                label: back.length ? 'Xem yêu cầu sửa' : 'Gửi duyệt',
                to: `/experiments/${first.id}${back.length ? '?tab=review' : ''}`,
              }
            : null,
        }
      }
      case 'review': {
        const waiting = data.waitingReviews
        const mineN = data.myReviews ?? 0
        if (waiting === null) {
          const n = count(exps, REVIEWING).length
          return {
            ...base,
            state: n ? 'active' : 'idle',
            status: n ? `${n} experiment đang được duyệt` : 'Reviewer độc lập kiểm tra kết quả',
          }
        }
        return {
          ...base,
          state: waiting + mineN > 0 ? 'action' : 'idle',
          status:
            waiting + mineN > 0
              ? [waiting && `${waiting} chờ nhận`, mineN && `${mineN} bạn đang duyệt`]
                  .filter(Boolean)
                  .join(', ')
              : 'Hàng đợi trống',
          cta: allowed
            ? {
                label: mineN ? 'Tiếp tục review' : waiting ? 'Nhận review' : 'Mở hàng đợi',
                to: mineN ? '/reviews?status=mine' : '/reviews',
              }
            : null,
        }
      }
      case 'report': {
        const n = data.readyReports
        return {
          ...base,
          state: n ? 'active' : 'idle',
          status:
            n === null
              ? 'Report PDF có mã xác minh công khai'
              : n
                ? `${n} report chính thức`
                : 'Chưa có report',
          cta: allowed && n ? { label: 'Xem report', to: '/reports' } : null,
        }
      }
    }
  })
}

/** Việc nên làm tiếp: bước đầu tiên đang chờ chính người dùng, ưu tiên việc cuối luồng. */
const PRIORITY: readonly StageId[] = ['review', 'submit', 'accounts', 'protocol', 'configure']

export function nextAction(stages: readonly StageView[]): StageView | null {
  for (const id of PRIORITY) {
    const stage = stages.find((s) => s.id === id)
    if (stage?.state === 'action' && stage.cta) return stage
  }
  return null
}

/** Bước hiện tại của luồng để tô sáng (bước có việc đang diễn ra muộn nhất). */
export function furthestActive(stages: readonly StageView[]): number {
  let last = -1
  stages.forEach((s, i) => {
    if (s.state !== 'idle') last = i
  })
  return last
}
