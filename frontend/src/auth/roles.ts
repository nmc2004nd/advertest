import type { Role } from '@/contracts/schemas'

/** Nhãn và mô tả role, định nghĩa một nơi (mission.md mục 3). */
export const ROLE_LABELS: Record<Role, string> = {
  engineer: 'Kỹ sư ML/perception',
  reviewer: 'Kỹ sư an toàn (reviewer)',
  admin: 'Quản trị viên',
}

export const ROLE_DESCRIPTIONS: Record<Role, string> = {
  engineer: 'Cấu hình và chạy experiment, phân tích metric, gửi kết quả đi duyệt.',
  reviewer: 'Tạo test protocol, review failure case, duyệt và xuất report.',
  admin: 'Duyệt tài khoản, gán role, quản lý model, attack catalog, máy chạy và ngân sách.',
}
