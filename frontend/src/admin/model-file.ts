// Đăng ký model qua web (requirements.md Phase R3, mục Admin catalog và model; mission.md nguyên
// tắc 10): chặn ngay ở client file không phải `.onnx`/`.safetensors`/`.pt`/`.pth` hoặc lớn hơn
// 500 MB. `.pt`/`.pth` không đăng ký trực tiếp: phải chuyển sang safetensors trong sandbox trên
// máy chủ trước (đề xuất contract 003).

/** `MODEL_UPLOAD_MAX_BYTES` của contract (`ModelUploadCreate.size_bytes`). */
export const MODEL_UPLOAD_MAX_BYTES = 500 * 1024 * 1024

/** `TORCHVISION_ARCHITECTURES` của contract: kiến trúc torchvision được phép. */
export const TORCHVISION_ARCHITECTURES = [
  'fasterrcnn_resnet50_fpn_v2',
  'retinanet_resnet50_fpn_v2',
  'fcos_resnet50_fpn',
] as const

/** `ULTRALYTICS_ARCHITECTURES` của contract: YOLO Ultralytics detect đăng ký bằng safetensors. */
export const ULTRALYTICS_ARCHITECTURES = [
  ...['n', 's', 'm', 'l', 'x'].map((s) => `yolov8${s}`),
  ...['t', 's', 'm', 'c', 'e'].map((s) => `yolov9${s}`),
  ...['n', 's', 'm', 'l', 'x'].map((s) => `yolo11${s}`),
  ...['n', 's', 'm', 'l', 'x'].map((s) => `yolo12${s}`),
] as const

/** `ULTRALYTICS_INPUT_SIZE` của contract. */
export const ULTRALYTICS_INPUT_SIZE = 640

const ALLOWED = /\.(onnx|safetensors|pt|pth)$/i
const PICKLE = /\.(pt|pth)$/i

/** File `.pt`/`.pth` (pickle): cần chuyển sang safetensors trong sandbox trước khi đăng ký. */
export function needsConversion(name: string): boolean {
  return PICKLE.test(name)
}

export type ConvertFramework = 'ultralytics' | 'torchvision'

/** Đoán loại checkpoint theo tên file: `.pth` thường là state dict torchvision. */
export function guessConvertFramework(name: string): ConvertFramework {
  return /\.pth$/i.test(name) && !/yolo/i.test(name) ? 'torchvision' : 'ultralytics'
}

/** Lỗi của file weights, `null` khi hợp lệ. */
export function weightsFileError(file: { name: string; size: number }): string | null {
  if (!ALLOWED.test(file.name) || /[/\\]/.test(file.name)) {
    return 'Chỉ nhận file .onnx, .safetensors, hoặc .pt/.pth (máy chủ chuyển sang .safetensors trong sandbox).'
  }
  if (file.size === 0) return 'File rỗng.'
  if (file.size > MODEL_UPLOAD_MAX_BYTES) return 'File lớn hơn 500 MB, giới hạn của upload qua web.'
  return null
}

/** Danh sách class: mỗi dòng hoặc mỗi đoạn ngăn bởi dấu phẩy là một class, theo thứ tự index. */
export function parseClassNames(text: string): string[] | Error {
  const names = text
    .split(/[\n,]/)
    .map((n) => n.trim())
    .filter((n) => n !== '')
  if (names.length === 0) return new Error('Nhập ít nhất một class.')
  const seen = new Set<string>()
  for (const name of names) {
    if (seen.has(name)) return new Error(`Class "${name}" bị lặp.`)
    seen.add(name)
  }
  return names
}
