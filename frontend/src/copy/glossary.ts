/**
 * Bảng thuật ngữ (requirements.md Phase R3, mục Thuật ngữ): mỗi định nghĩa tối đa 2 câu. Component
 * `Term` (`components/Term.tsx`) hiện định nghĩa trong tooltip.
 */
export interface GlossaryEntry {
  /** Cách viết thuật ngữ trong câu. */
  term: string
  definition: string
}

export const GLOSSARY = {
  map: {
    term: 'mAP',
    definition:
      'Độ chính xác trung bình của model trên mọi class, từ 0 đến 1, càng cao càng tốt. Ở đây tính với ngưỡng trùng khớp IoU 0.5 (mAP@0.5).',
  },
  ap50: {
    term: 'AP50',
    definition:
      'Độ chính xác của model trên một class, tính với ngưỡng trùng khớp IoU 0.5. Trung bình AP50 của mọi class là mAP.',
  },
  relative_drop: {
    term: 'mức sụt tương đối',
    definition:
      'mAP giảm bao nhiêu phần trăm so với ảnh sạch. Ví dụ mAP từ 0.80 xuống 0.40 là sụt 50%.',
  },
  breaking_point: {
    term: 'điểm gãy',
    definition:
      'Level nhỏ nhất của attack làm mức sụt vượt ngưỡng của protocol. Điểm gãy càng lớn thì model càng bền.',
  },
  level: {
    term: 'level',
    definition:
      'Cường độ của attack, ví dụ eps của FGSM hay độ dày của sương mù. Level càng cao thì ảnh bị biến đổi càng mạnh.',
  },
  white_box: {
    term: 'attack white-box',
    definition:
      'Attack dùng gradient của chính model để tìm nhiễu khó thấy mà làm model sai nhiều nhất. Chỉ chạy được với model hỗ trợ gradient.',
  },
  corruption: {
    term: 'corruption',
    definition:
      'Biến đổi ảnh mô phỏng điều kiện thực tế như sương mù, mưa, nhiễu cảm biến hay mờ chuyển động. Không cần biết gì về model.',
  },
  occlusion: {
    term: 'occlusion',
    definition:
      'Che một phần object, ví dụ bằng khối màu hay vật cản. Dùng để xem model còn nhận ra object khi chỉ thấy một phần.',
  },
  patch: {
    term: 'patch',
    definition:
      'Miếng hình in được, dán lên ảnh để đánh lừa model. Patch được huấn luyện trước trên dữ liệu rồi áp lên ảnh kiểm thử.',
  },
  slice: {
    term: 'slice',
    definition:
      'Tập ảnh con của một dataset, chọn theo điều kiện như ban đêm hay trời mưa. Mỗi slice định danh bằng hash nên chạy lại cho đúng cùng ảnh.',
  },
  protocol: {
    term: 'protocol',
    definition:
      'Bộ tiêu chí kiểm thử do reviewer chốt trước khi chạy: attack bắt buộc, level, slice tối thiểu và ngưỡng đạt. Experiment Chính thức phải chạy đủ protocol.',
  },
  fingerprint: {
    term: 'fingerprint',
    definition:
      'Mã hash của mọi đầu vào một run: model, ảnh, attack, tham số và phiên bản thư viện. Hai run cùng fingerprint là cùng một phép thử.',
  },
  exploration: {
    term: 'Khám phá',
    definition:
      'Experiment thử tự do, không theo protocol nào. Không gửi duyệt được và không dùng làm kết quả của report.',
  },
  official: {
    term: 'Chính thức',
    definition:
      'Experiment chạy theo một protocol đã chốt. Chỉ experiment Chính thức mới gửi duyệt và có report.',
  },
} as const satisfies Record<string, GlossaryEntry>

export type GlossaryKey = keyof typeof GLOSSARY
