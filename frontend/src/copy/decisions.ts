/**
 * Ý nghĩa của 5 quyết định (requirements.md Phase R3, mục Ý nghĩa quyết định): điều gì xảy ra ngay,
 * ai làm bước tiếp theo, có đảo ngược được không. Nội dung khớp hành vi Phase 8.
 */
export type DecisionKey = 'submit' | 'approve' | 'changes_requested' | 'reject' | 'export'

export interface DecisionMeaning {
  label: string
  now: string
  next: string
  reversible: string
}

export const DECISIONS: Record<DecisionKey, DecisionMeaning> = {
  submit: {
    label: 'Gửi duyệt',
    now: 'Experiment bị khóa: không hủy, không sửa, không chạy thêm run được; chỉ còn bình luận.',
    next: 'Một reviewer khác bạn nhận review, xem các case bắt buộc rồi ra quyết định.',
    reversible: 'Không rút lại được. Muốn đổi cấu hình thì nhân bản thành experiment mới.',
  },
  approve: {
    label: 'Chấp nhận',
    now: 'Review kết thúc ở trạng thái Đã duyệt; report chính thức có mã xác minh được sinh ngay.',
    next: 'Kỹ sư và reviewer đọc report; người có quyền xuất report tải file PDF hoặc JSON.',
    reversible:
      'Không đảo ngược được. Kết luận về model có thể là không đạt dù bài test được chấp nhận.',
  },
  changes_requested: {
    label: 'Yêu cầu sửa',
    now: 'Review kết thúc; experiment giữ nguyên kết quả và lý do bạn ghi.',
    next: 'Kỹ sư nhân bản experiment, sửa theo lý do rồi chạy và gửi duyệt lại.',
    reversible: 'Không đảo ngược được trên experiment này; lần gửi sau là một experiment mới.',
  },
  reject: {
    label: 'Từ chối',
    now: 'Review kết thúc ở trạng thái Từ chối; không có report.',
    next: 'Không ai cần làm gì thêm với experiment này. Kỹ sư đọc lý do trong tab Review.',
    reversible: 'Không đảo ngược được.',
  },
  export: {
    label: 'Xuất report',
    now: 'Bạn tải đúng file đã lưu lúc duyệt; mỗi lần tải được ghi vào audit log.',
    next: 'Người nhận kiểm tra file bằng trang xác minh, so mã sha256 với bản đã lưu.',
    reversible:
      'Report không sửa được. Nếu sinh file lỗi thì chỉ sinh lại từ cùng dữ liệu đã duyệt.',
  },
}

/** Câu nhắc nguyên tắc 8 (mission.md) trên trang report. */
export const TEST_ENVIRONMENT_NOTE =
  'Kết quả chỉ đo trong môi trường kiểm thử, trên dữ liệu và mô phỏng. Không dùng làm căn cứ triển khai thật khi chưa được kiểm chứng bằng quy trình khác.'
