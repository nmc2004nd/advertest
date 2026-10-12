/**
 * Câu chữ xóa, lưu trữ model và class mapping qua web (Phase R3, đề xuất contract 002).
 */
export const MODEL_ADMIN_COPY = {
  mappingTitle: 'Class mapping',
  mappingIntro:
    'Chọn class của model ứng với từng class của dataset. Wizard cần mapping này để chấm model trên dataset.',
  mappingHint:
    'Gợi ý sẵn theo preset KITTI → COCO hoặc tên class trùng nhau; sửa nếu cần. Class bỏ qua thành vùng bỏ qua khi chấm.',
  createMappingNow: 'Tạo class mapping ngay',
  noDataset:
    'Chưa có dataset nào. Admin nhập dataset bằng CLI trước, rồi thêm mapping ở trang model.',
  difficultyHint: 'Moderate bỏ qua object quá nhỏ, che khuất hoặc bị cắt nhiều (chuẩn KITTI).',
  moderate: 'Moderate (cao ≥ 25 px, che ≤ 1, cắt ≤ 30%)',
  noMapping: 'Model chưa có class mapping nên chưa chọn được trong wizard.',
  addMapping: 'Thêm class mapping',
  saveMapping: 'Lưu class mapping',
  mappingSaved: 'Đã lưu class mapping.',
  mappingFailedAfterRegister: (reason: string) =>
    `Model đã đăng ký nhưng chưa tạo được class mapping: ${reason} Thêm lại ở mục Class mapping bên dưới.`,
  notOwner: (owner: string | null | undefined) =>
    `Model do ${owner ?? 'người khác'} đăng ký. Chỉ người đăng ký hoặc admin được kiểm tra lại, lưu trữ, xóa hay thêm class mapping; model không cần dùng thì bạn chỉ cần không chọn nó.`,
  archive: 'Lưu trữ',
  restore: 'Khôi phục',
  delete: 'Xóa model',
  archivedNote:
    'Model đã lưu trữ: không chọn được cho experiment, thử nhanh hay mapping mới. Experiment và report cũ vẫn xem được.',
  archiveTitle: 'Lưu trữ model?',
  archiveConsequence:
    'Model bị ẩn khỏi wizard và thử nhanh. Experiment, run và report đã có vẫn giữ nguyên. Khôi phục được bất cứ lúc nào.',
  deleteTitle: 'Xóa model?',
  deleteConsequence:
    'Xóa hẳn model, weights và class mapping của nó; không hoàn tác được. Model đã dùng trong experiment hoặc thử nhanh không xóa được, chỉ lưu trữ được.',
  convertTitle: 'File .pt cần chuyển sang .safetensors',
  convertIntro:
    'File .pt là pickle, mở ra có thể chạy mã tùy ý. Máy chủ chuyển nó sang .safetensors trong sandbox riêng (không mạng, không truy cập dữ liệu, giới hạn tài nguyên) rồi xóa file .pt; model sau đó vẫn được kiểm tra như mọi model.',
  convertFramework: 'Loại checkpoint',
  convertButton: 'Chuyển sang safetensors',
  convertQueued: 'Đang chờ sandbox chuyển đổi…',
  convertRunning: 'Sandbox đang chuyển đổi…',
  convertDone:
    'Đã chuyển sang .safetensors. Các trường bên dưới đã điền theo checkpoint; kiểm tra rồi bấm Đăng ký.',
  convertRetry: 'Thử lại',
  convertFirst: 'Chuyển file .pt sang safetensors trước khi đăng ký.',
  convertedNotOnnx: 'File đã chuyển là .safetensors: chọn framework ultralytics hoặc torchvision.',
} as const
