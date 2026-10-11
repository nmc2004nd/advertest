/**
 * Câu chữ của wizard 3 bước (requirements.md Phase R3, Wizard 3 bước). Chuỗi cũ của wizard 6 bước
 * vẫn nằm trong component, chờ Phase R3b gom.
 */
import type { AttackSpecMetadata } from '@/contracts/api'

export const WIZARD_INTRO =
  'Ba bước: chọn mục đích, chọn model và dữ liệu, rồi xem attack hệ thống đề xuất. Nháp được lưu tự động trên trình duyệt này; rời trang rồi quay lại vẫn còn.'

export const MODE_CARD = {
  exploration: {
    title: 'Khám phá',
    description: 'Thử tự do theo protocol dev. Không gửi duyệt được; dùng để tìm điểm yếu nhanh.',
  },
  official: {
    title: 'Chính thức',
    description: 'Chạy theo protocol do reviewer chốt trước. Gửi duyệt và xuất report được.',
  },
} as const

export const STEP_TWO_HINT =
  'Chọn model cần kiểm định, ảnh để thử và máy chạy. Chạm giới hạn thời gian thì experiment dừng và giữ kết quả đã có.'

export const STEP_THREE_HINT =
  'Danh sách attack dựng từ preset và protocol đã chọn. Bấm chip để bật hoặc tắt level; ước lượng cập nhật ngay.'

export const REALISM_LABEL: Record<AttackSpecMetadata['realism'], string> = {
  low: 'Ít sát thực tế',
  medium: 'Khá sát thực tế',
  high: 'Rất sát thực tế',
}

export const PROTOCOL_REQUIRED = 'Protocol yêu cầu'
export const ADVANCED = 'Tùy chỉnh nâng cao'
export const ADD_ATTACK = 'Thêm attack'
export const SEARCH_ROW =
  'Tự tìm ngưỡng: hệ thống dò level nhỏ nhất làm model gãy thay cho quét lưới.'
export const LIMIT_LABEL = 'Giới hạn thời gian'
export const SUGGESTED_LIMIT = (minutes: number, max: number) =>
  `Gợi ý ${minutes} phút (mặc định của máy), tối đa ${max} phút.`
export const NO_READY_MODEL =
  'Chưa có model nào sẵn sàng. Model mới đăng ký cần qua bước kiểm tra trước khi dùng được.'
