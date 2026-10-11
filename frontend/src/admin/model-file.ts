// Đăng ký model qua web (requirements.md Phase R3, mục Admin catalog và model; mission.md nguyên
// tắc 10): chặn ngay ở client file không phải `.onnx`/`.safetensors` hoặc lớn hơn 500 MB.

/** `MODEL_UPLOAD_MAX_BYTES` của contract (`ModelUploadCreate.size_bytes`). */
export const MODEL_UPLOAD_MAX_BYTES = 500 * 1024 * 1024

/** `TORCHVISION_ARCHITECTURES` của contract: kiến trúc torchvision được phép. */
export const TORCHVISION_ARCHITECTURES = [
  'fasterrcnn_resnet50_fpn_v2',
  'retinanet_resnet50_fpn_v2',
  'fcos_resnet50_fpn',
] as const

const ALLOWED = /\.(onnx|safetensors)$/i

/** Lỗi của file weights, `null` khi hợp lệ. */
export function weightsFileError(file: { name: string; size: number }): string | null {
  if (!ALLOWED.test(file.name) || /[/\\]/.test(file.name)) {
    return 'Chỉ nhận file .onnx hoặc .safetensors. File .pt và pickle không được tải lên vì có thể chạy mã tùy ý.'
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
