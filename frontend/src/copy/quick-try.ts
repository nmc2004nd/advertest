/** Câu chữ của trang thử nhanh (requirements.md Phase R3, mục Thử nhanh; design.md mục 7). */
export const QUICK_TRY_COPY = {
  title: 'Thử nhanh',
  description:
    'Áp một attack lên một ảnh để xem model giữ được và mất những object nào. Chỉ để minh họa, không phải kiểm thử.',
  formTitle: 'Chọn model, attack và ảnh',
  // Gợi ý attack ghép quanh hai thuật ngữ `patch` và `white_box` (bọc bằng `Term` ở trang).
  attackHint: {
    noPatch: 'Không có attack',
    gradient: 'Attack cần gradient',
    gradientRest: 'chỉ hiện khi model hỗ trợ gradient.',
  },
  imageHint: 'JPEG hoặc PNG, tối đa 10 MB. Kéo ảnh thả vào đây hoặc chọn file.',
  imageMissing: 'Chọn một ảnh.',
  submit: 'Chạy thử nhanh',
  submitting: 'Đang gửi…',
  busy: 'Bạn đang có một lượt thử chưa xong.',
  busyLink: 'Xem lượt đang chạy',
  busyNoLink: 'Chờ lượt đó xong rồi thử lại.',
  pending: 'Worker đang chạy attack trên ảnh. Trang tự cập nhật mỗi 2 giây.',
  failed: 'Lượt thử thất bại',
  gone: 'Lượt thử đã hết hạn và bị xóa',
  goneDetail: 'Kết quả thử nhanh chỉ giữ 24 giờ.',
  notFound: 'Không tìm thấy lượt thử này',
  notFoundDetail: 'Lượt thử chỉ người tạo xem được.',
  retry: 'Thử lại',
  notATestResult: 'Không phải kết quả kiểm thử',
  notATestResultDetail: (time: string) =>
    `Không tạo experiment và không vào report. Ảnh tự xóa sau 24 giờ, lúc ${time}.`,
  level: 'Level',
  clean: 'Ảnh sạch',
  attacked: 'Sau tấn công',
  layers: 'Lớp box',
  layerLabels: {
    clean: 'Dự đoán ảnh sạch',
    attacked: 'Giữ được',
    lost: 'Bị mất',
    fresh: 'Phát hiện sai mới',
  },
  table: {
    caption: 'Object theo level đang chọn',
    className: 'Class',
    cleanScore: 'Score sạch',
    attackedScore: 'Score sau tấn công',
    status: 'Trạng thái',
    empty: 'Model không thấy object nào trên ảnh này.',
  },
} as const
