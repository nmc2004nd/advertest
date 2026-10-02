/** Nhãn tiếng Việt của vòng review (Phase 8); một nơi để engineer và reviewer dùng chung. */
import type {
  ExperimentDetail,
  ExperimentStatus,
  ModelVerdict,
  ReviewDecision,
  SubmitCheckItem,
} from '@/contracts/api'

export const DECISION_LABEL: Record<ReviewDecision, string> = {
  approve: 'Chấp nhận',
  changes_requested: 'Yêu cầu sửa',
  reject: 'Từ chối',
}

export const MODEL_VERDICT_LABEL: Record<ModelVerdict, string> = {
  meets_criteria: 'Model đạt tiêu chí',
  does_not_meet: 'Model không đạt tiêu chí',
  conditional: 'Model đạt có điều kiện',
}

export const SUBMIT_CHECK_LABEL: Record<SubmitCheckItem['code'], string> = {
  experiment_completed: 'Experiment đã hoàn thành',
  protocol_not_dev: 'Protocol không phải bản phát triển',
  runs_final: 'Mọi run bắt buộc đã kết thúc',
  no_dirty_runs: 'Không có run chạy từ code chưa commit',
  required_cases_visible: 'Case bắt buộc đã làm mờ',
}

/** Trạng thái đã gửi duyệt (experiment bị khóa). */
export const LOCKED_STATUSES: readonly ExperimentStatus[] = [
  'submitted_for_review',
  'in_review',
  'approved',
  'changes_requested',
  'rejected',
]

/** Đang chờ hoặc đang review: còn bình luận được. */
export const OPEN_REVIEW: readonly ExperimentStatus[] = ['submitted_for_review', 'in_review']

/** Câu của dải "Đã khóa" theo trạng thái. */
export function lockedBannerText(status: ExperimentStatus): string | null {
  switch (status) {
    case 'submitted_for_review':
      return 'Đã khóa – đang chờ duyệt'
    case 'in_review':
      return 'Đã khóa – đang được review'
    case 'approved':
      return 'Đã khóa – đã được chấp nhận'
    case 'changes_requested':
      return 'Đã khóa – reviewer yêu cầu sửa: nhân bản để tạo experiment mới'
    case 'rejected':
      return 'Đã khóa – đã bị từ chối'
    default:
      return null
  }
}

/** Đủ điều kiện gửi duyệt (mọi mục `submit_check` thỏa). */
export function canSubmit(experiment: ExperimentDetail): boolean {
  const checks = experiment.submit_check ?? []
  return checks.length > 0 && checks.every((item) => item.satisfied)
}
