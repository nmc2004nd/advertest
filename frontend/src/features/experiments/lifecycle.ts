import type { ExperimentDetail } from '@/contracts/api'

/**
 * Thanh vòng đời ở đầu trang experiment (requirements.md Phase R3, mục Trang experiment): Tạo →
 * Chạy → Phân tích → Gửi duyệt → Review → Report, suy hoàn toàn từ `ExperimentDetail`. Experiment
 * Khám phá chỉ có 3 bước đầu (nguyên tắc 11).
 *
 * Bước Chạy hiện `failed` khi experiment đã kết thúc mà có run thất bại (người duyệt chốt
 * 2026-10-11: `ExperimentStatus` không có giá trị `failed`).
 */
export type LifecycleStepId = 'create' | 'run' | 'analyze' | 'submit' | 'review' | 'report'
export type LifecycleState = 'done' | 'current' | 'todo' | 'failed'

export interface LifecycleStep {
  id: LifecycleStepId
  label: string
  state: LifecycleState
  /** Một dòng nói rõ vì sao bước ở trạng thái này (nguyên tắc 6). */
  detail: string
  /** `failed` nhẹ (yêu cầu sửa): tông cảnh báo thay cho tông lỗi. */
  warning?: boolean
}

export type LifecycleInput = Pick<
  ExperimentDetail,
  'status' | 'mode' | 'run_counts' | 'review' | 'report'
>

const LABEL: Record<LifecycleStepId, string> = {
  create: 'Tạo',
  run: 'Chạy',
  analyze: 'Phân tích',
  submit: 'Gửi duyệt',
  review: 'Review',
  report: 'Report',
}

function step(
  id: LifecycleStepId,
  state: LifecycleState,
  detail: string,
  warning = false,
): LifecycleStep {
  return warning
    ? { id, label: LABEL[id], state, detail, warning }
    : { id, label: LABEL[id], state, detail }
}

function runStep(e: LifecycleInput): LifecycleStep {
  switch (e.status) {
    case 'draft':
      return step('run', 'todo', 'Chưa xếp hàng')
    case 'queued':
      return step('run', 'current', 'Đang chờ máy')
    case 'running':
      return step('run', 'current', 'Đang chạy')
    default: {
      const failed = e.run_counts.failed
      if (failed > 0) return step('run', 'failed', `${failed} run thất bại`)
      return step('run', 'done', e.status === 'cancelled' ? 'Đã hủy, giữ kết quả' : 'Xong')
    }
  }
}

function analyzeStep(e: LifecycleInput): LifecycleStep {
  if (e.review) return step('analyze', 'done', 'Đã xem kết quả')
  if (e.status === 'completed' || e.status === 'cancelled') {
    return step('analyze', 'current', 'Xem kết quả và failure case')
  }
  return step('analyze', 'todo', 'Sau khi chạy xong')
}

function reviewStep(e: LifecycleInput): LifecycleStep {
  const review = e.review
  if (!review) return step('review', 'todo', 'Sau khi gửi duyệt')
  switch (review.decision) {
    case null:
      return step('review', 'current', review.assignee ? 'Đang được review' : 'Chờ reviewer nhận')
    case 'approve':
      return step('review', 'done', 'Đã chấp nhận')
    case 'changes_requested':
      return step('review', 'failed', 'Yêu cầu sửa', true)
    case 'reject':
      return step('review', 'failed', 'Từ chối')
  }
}

function reportStep(e: LifecycleInput): LifecycleStep {
  const report = e.report
  if (!report) {
    return e.status === 'approved'
      ? step('report', 'current', 'Đang sinh report')
      : step('report', 'todo', 'Sau khi được chấp nhận')
  }
  switch (report.status) {
    case 'generating':
      return step('report', 'current', 'Đang sinh report')
    case 'ready':
      return step('report', 'done', 'Sẵn sàng')
    case 'failed':
      return step('report', 'failed', 'Sinh lỗi')
  }
}

export function lifecycle(e: LifecycleInput): LifecycleStep[] {
  const steps = [step('create', 'done', 'Đã tạo'), runStep(e), analyzeStep(e)]
  if (e.mode === 'exploration') return steps
  return [
    ...steps,
    e.review
      ? step('submit', 'done', 'Đã gửi, đã khóa')
      : step('submit', 'todo', 'Khi mọi run bắt buộc đã xong'),
    reviewStep(e),
    reportStep(e),
  ]
}
