/**
 * Câu chữ của admin catalog, duyệt spec và đăng ký model (requirements.md Phase R3, mục Admin
 * catalog và model).
 */
import type { AttackSpecMetadata, SpecCheckName } from '@/contracts/schemas'

/** Bảy mục tự kiểm tra, theo thứ tự `SpecCheckName`. */
export const SPEC_CHECK_LABEL: Record<SpecCheckName, { label: string; hint: string }> = {
  runs: {
    label: 'Chạy được',
    hint: 'Dựng và áp attack không lỗi ở level nhỏ nhất, giữa và lớn nhất.',
  },
  value_range: {
    label: 'Giá trị ảnh hợp lệ',
    hint: 'Ảnh ra là float32 trong [0, 1], đúng kích thước.',
  },
  pad_unchanged: {
    label: 'Giữ nguyên vùng đệm',
    hint: 'Phần viền letterbox không bị thay đổi.',
  },
  identity: {
    label: 'Level 0 không biến đổi',
    hint: 'Ở level "không biến đổi", ảnh ra giống hệt ảnh vào.',
  },
  batch_invariant: {
    label: 'Không phụ thuộc batch',
    hint: 'Chạy batch 1 và batch 4 cho cùng kết quả.',
  },
  norm_bound: { label: 'Nhiễu trong giới hạn', hint: 'Attack: chuẩn của nhiễu không vượt eps.' },
  deterministic: { label: 'Tái lập được', hint: 'Hai lần chạy cùng seed cho ảnh giống hệt.' },
}

export const REALISM_LABEL: Record<AttackSpecMetadata['realism'], string> = {
  low: 'Thấp',
  medium: 'Trung bình',
  high: 'Cao',
}

export const CATALOG_COPY = {
  unsupportedAdapter: 'Adapter này chưa hỗ trợ tạo qua giao diện.',
  checkingNote: 'Worker đang tự kiểm tra spec. Trang tự cập nhật khi có kết quả.',
  rejectedNote:
    'Reviewer đã từ chối spec này. Spec bị từ chối không sửa được; muốn tiếp tục thì tạo version mới từ spec này.',
  approveConsequence:
    'Spec chuyển sang Đang dùng và xuất hiện trong wizard. Version đang dùng cùng tên (nếu có) chuyển sang Đã thay thế; experiment cũ vẫn giữ version chúng đã chạy.',
  rejectConsequence: 'Spec quay về Nháp; người tạo thấy lý do và phải tạo version mới để gửi lại.',
  ownSpec: 'Bạn đã tạo spec này. Một reviewer khác phải kích hoạt.',
  onnxLayouts: {
    intro: 'Đầu ra ONNX phải theo một trong hai layout:',
    yolo: 'Kiểu YOLO: một tensor (1, 4+C, N), 4 tọa độ box cộng C điểm class cho N box.',
    nms: 'Ba tensor boxes/scores/labels, đã qua NMS.',
    outro: 'Model theo layout khác sẽ kiểm tra không đạt.',
  },
} as const
