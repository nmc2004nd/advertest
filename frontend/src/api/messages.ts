import type { ErrorCode } from '@/contracts/schemas'

import { ApiError } from './errors'

/** Thông điệp tiếng Việt cho mọi ErrorCode (thiếu mã nào thì tsc báo lỗi). */
export const ERROR_MESSAGES: Record<ErrorCode, string> = {
  not_implemented: 'Chức năng này chưa có.',
  unauthenticated: 'Bạn cần đăng nhập để tiếp tục.',
  forbidden: 'Bạn không có quyền thực hiện thao tác này.',
  not_found: 'Không tìm thấy dữ liệu.',
  conflict: 'Thao tác không thực hiện được ở trạng thái hiện tại.',
  invalid_request: 'Yêu cầu không hợp lệ.',
  invalid_credentials: 'Email hoặc mật khẩu không đúng.',
  account_pending: 'Tài khoản đang chờ admin duyệt.',
  account_rejected: 'Yêu cầu truy cập đã bị từ chối.',
  account_disabled: 'Tài khoản đã bị vô hiệu hóa.',
  rate_limited: 'Đăng nhập sai quá nhiều lần. Vui lòng thử lại sau 15 phút.',
  csrf_failed: 'Phiên làm việc không hợp lệ. Vui lòng tải lại trang.',
  validation_error: 'Dữ liệu nhập chưa hợp lệ.',
  not_supported_yet: 'Tính năng này chưa có ở phiên bản hiện tại.',
  queue_limit_reached:
    'Bạn đã có 3 experiment đang chờ. Hãy chờ một experiment chạy xong rồi tạo tiếp.',
  internal_error: 'Máy chủ gặp lỗi. Vui lòng thử lại sau.',
  not_compliant: 'Cấu hình chưa tuân thủ protocol đã chọn.',
  experiment_locked: 'Experiment đã gửi duyệt nên bị khóa, không sửa được.',
  checklist_incomplete: 'Chưa đủ điều kiện để chấp nhận.',
  quick_try_busy: 'Bạn đang có một lượt thử nhanh chưa xong. Vui lòng chờ lượt đó kết thúc.',
  gone: 'Kết quả thử nhanh đã hết hạn và bị xóa.',
}

export const UNKNOWN_ERROR_MESSAGE = 'Đã có lỗi xảy ra. Vui lòng thử lại.'

/**
 * Thông điệp cho người dùng. Lỗi nghiệp vụ (409, 422) giữ thông điệp cụ thể của server; các mã
 * còn lại dùng thông điệp chung ở trên.
 */
export function errorMessage(error: unknown): string {
  if (!(error instanceof ApiError) || error.code === 'unknown') return UNKNOWN_ERROR_MESSAGE
  if (error.code === 'conflict' || error.code === 'invalid_request') {
    return error.message || ERROR_MESSAGES[error.code]
  }
  return ERROR_MESSAGES[error.code]
}
