import { can } from '@/auth/permissions'
import type { ExperimentDetail, Me } from '@/contracts/api'

export type Tone = 'info' | 'action' | 'success' | 'warning' | 'danger' | 'muted'

export interface NextStepView {
  tone: Tone
  title: string
  body: string
  primary?: { label: string; to?: string; onClick?: true }
  secondary?: { label: string; to: string }
}

/**
 * Bước tiếp theo của một experiment trong luồng chính (docs/demo-mvp.md), theo trạng thái và
 * quyền của người đang xem. `onClick: true` = nút mở hộp gửi duyệt.
 */
export function nextStep(
  e: ExperimentDetail,
  me: Pick<Me, 'id' | 'roles'> | undefined,
  canOpenSubmit: boolean,
): NextStepView | null {
  const owner = me?.id === e.owner.id
  const reviewer = can(me, 'review.decide') && !owner
  const done = e.progress.images_done
  const total = e.progress.images_total
  switch (e.status) {
    case 'queued':
      return {
        tone: 'info',
        title: 'Đang chờ máy chạy',
        body: `${e.queue_position !== null ? `Vị trí ${e.queue_position} trong hàng đợi của ${e.compute_target.name}. ` : ''}Bạn có thể rời trang; trang tự cập nhật và hệ thống gửi email khi xong.`,
      }
    case 'running':
      return {
        tone: 'info',
        title: 'Worker đang chạy attack',
        body: `Đã xử lý ${done}/${total} ảnh. Kết quả từng run hiện ngay khi run đó xong.`,
        secondary: { label: 'Xem kết quả tạm', to: '?tab=results' },
      }
    case 'completed':
      if (canOpenSubmit)
        return {
          tone: 'action',
          title: 'Kết quả đã sẵn sàng để gửi duyệt',
          body: 'Xem nhanh failure case để chắc kết quả hợp lý, rồi gửi cho một reviewer độc lập. Sau khi gửi, experiment bị khóa.',
          primary: { label: 'Gửi duyệt', onClick: true },
          secondary: { label: 'Xem failure case', to: '?tab=cases' },
        }
      if (owner && e.protocol.status === 'dev' && can(me, 'experiment.create'))
        return {
          tone: 'warning',
          title: 'Protocol dev không vào được bước duyệt',
          body: 'Kết quả này chỉ để thử. Nhân bản experiment, chọn một protocol chính thức ở bước 1 rồi chạy lại để có kết luận được duyệt.',
          primary: { label: 'Nhân bản với protocol khác', to: `/experiments/new?clone=${e.id}` },
          secondary: { label: 'Xem kết quả', to: '?tab=results' },
        }
      return {
        tone: 'muted',
        title: 'Đã chạy xong',
        body: owner
          ? 'Experiment chưa đủ điều kiện để gửi đi.'
          : `Đang chờ ${e.owner.full_name} xem kết quả và gửi đi.`,
        secondary: { label: 'Xem kết quả', to: '?tab=results' },
      }
    case 'submitted_for_review':
      return {
        tone: reviewer ? 'action' : 'info',
        title: reviewer ? 'Experiment này đang chờ reviewer nhận' : 'Đang chờ một reviewer nhận',
        body: reviewer
          ? 'Nhận review để xem các case bắt buộc và ra quyết định.'
          : 'Bạn sẽ nhận email khi có quyết định. Trao đổi với reviewer ở tab Review.',
        primary: reviewer ? { label: 'Mở để review', to: `/reviews/${e.id}` } : undefined,
        secondary: reviewer ? undefined : { label: 'Mở tab Review', to: '?tab=review' },
      }
    case 'in_review':
      return {
        tone: reviewer ? 'action' : 'info',
        title: 'Đang được review',
        body: e.review?.assignee
          ? `${e.review.assignee.full_name} đang xem các case bắt buộc.`
          : 'Reviewer đang xem các case bắt buộc.',
        primary: reviewer ? { label: 'Tiếp tục review', to: `/reviews/${e.id}` } : undefined,
        secondary: { label: 'Mở tab Review', to: '?tab=review' },
      }
    case 'approved':
      return {
        tone: 'success',
        title: 'Đã chấp nhận: có report chính thức',
        body: 'Report PDF mang mã xác minh; người ngoài kiểm tra được file bằng trang xác minh công khai.',
        primary: e.report ? { label: 'Xem report', to: `/reports/${e.report.id}` } : undefined,
        secondary: { label: 'Đọc quyết định', to: '?tab=review' },
      }
    case 'changes_requested':
      return {
        tone: 'warning',
        title: 'Reviewer yêu cầu sửa',
        body: 'Đọc nhận xét ở tab Review, rồi nhân bản để sửa cấu hình và chạy lại. Bản này giữ nguyên làm lịch sử.',
        secondary: { label: 'Đọc nhận xét', to: '?tab=review' },
      }
    case 'rejected':
      return {
        tone: 'danger',
        title: 'Đã bị từ chối',
        body: 'Lý do nằm ở tab Review.',
        secondary: { label: 'Đọc lý do', to: '?tab=review' },
      }
    default:
      return null
  }
}
