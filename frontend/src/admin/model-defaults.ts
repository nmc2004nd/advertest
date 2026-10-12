// Giá trị mặc định khi đăng ký model qua web: đọc metadata ngay trong file weights (không upload
// trước), cộng các bộ class và kích thước đầu vào hay dùng để người dùng chọn thay vì gõ.

/** COCO 80 class theo thứ tự index của YOLO / Ultralytics (như fixture `yolov8n.onnx`). */
export const COCO80 = [
  'person', 'bicycle', 'car', 'motorcycle', 'airplane', 'bus', 'train', 'truck', 'boat',
  'traffic light', 'fire hydrant', 'stop sign', 'parking meter', 'bench', 'bird', 'cat', 'dog',
  'horse', 'sheep', 'cow', 'elephant', 'bear', 'zebra', 'giraffe', 'backpack', 'umbrella',
  'handbag', 'tie', 'suitcase', 'frisbee', 'skis', 'snowboard', 'sports ball', 'kite',
  'baseball bat', 'baseball glove', 'skateboard', 'surfboard', 'tennis racket', 'bottle',
  'wine glass', 'cup', 'fork', 'knife', 'spoon', 'bowl', 'banana', 'apple', 'sandwich', 'orange',
  'broccoli', 'carrot', 'hot dog', 'pizza', 'donut', 'cake', 'chair', 'couch', 'potted plant',
  'bed', 'dining table', 'toilet', 'tv', 'laptop', 'mouse', 'remote', 'keyboard', 'cell phone',
  'microwave', 'oven', 'toaster', 'sink', 'refrigerator', 'book', 'clock', 'vase', 'scissors',
  'teddy bear', 'hair drier', 'toothbrush',
] // prettier-ignore

const COCO91_RAW = [
  '__background__', 'person', 'bicycle', 'car', 'motorcycle', 'airplane', 'bus', 'train', 'truck',
  'boat', 'traffic light', 'fire hydrant', 'N/A', 'stop sign', 'parking meter', 'bench', 'bird',
  'cat', 'dog', 'horse', 'sheep', 'cow', 'elephant', 'bear', 'zebra', 'giraffe', 'N/A',
  'backpack', 'umbrella', 'N/A', 'N/A', 'handbag', 'tie', 'suitcase', 'frisbee', 'skis',
  'snowboard', 'sports ball', 'kite', 'baseball bat', 'baseball glove', 'skateboard', 'surfboard',
  'tennis racket', 'bottle', 'N/A', 'wine glass', 'cup', 'fork', 'knife', 'spoon', 'bowl',
  'banana', 'apple', 'sandwich', 'orange', 'broccoli', 'carrot', 'hot dog', 'pizza', 'donut',
  'cake', 'chair', 'couch', 'potted plant', 'bed', 'N/A', 'dining table', 'N/A', 'N/A', 'toilet',
  'N/A', 'tv', 'laptop', 'mouse', 'remote', 'keyboard', 'cell phone', 'microwave', 'oven',
  'toaster', 'sink', 'refrigerator', 'N/A', 'book', 'clock', 'vase', 'scissors', 'teddy bear',
  'hair drier', 'toothbrush',
] // prettier-ignore

/**
 * Tên class không được trùng (contract `ModelRegister`): tên lặp (ví dụ "N/A" của COCO torchvision)
 * thêm hậu tố index, như test nghiệm thu Phase R2 đăng ký fixture torchvision.
 */
export function uniqueNames(raw: readonly string[]): string[] {
  return raw.map((n, i) => (raw.indexOf(n) !== raw.lastIndexOf(n) ? `${n}_${i}` : n))
}

/** COCO 91 class của weights torchvision `COCO_V1` (gồm `__background__` và các ô "N/A"). */
export const COCO91_TORCHVISION = uniqueNames(COCO91_RAW)

export type ClassPreset = 'file' | 'coco80' | 'coco91' | 'custom'

export const CLASS_PRESETS: Record<
  Exclude<ClassPreset, 'file'>,
  { label: string; names: string[] }
> = {
  coco80: { label: 'COCO 80 class (YOLO, Ultralytics)', names: COCO80 },
  coco91: { label: 'COCO 91 class (torchvision COCO_V1)', names: COCO91_TORCHVISION },
  custom: { label: 'Tự nhập danh sách', names: [] },
}

/** Kích thước đầu vào hay dùng (cạnh ảnh vuông sau letterbox). */
export const INPUT_SIZES = [320, 416, 512, 640, 800, 1024] as const
export const DEFAULT_INPUT_SIZE = 640

/** Mô tả kiến trúc ONNX hay gặp; người dùng vẫn chọn "Khác" để tự nhập. */
export const ONNX_ARCHITECTURES = [
  'YOLOv8 (Ultralytics) xuất ONNX',
  'YOLO11 (Ultralytics) xuất ONNX',
  'YOLOv5 xuất ONNX',
  'RT-DETR xuất ONNX',
  'Model có đầu ra boxes/scores/labels (đã NMS)',
] as const

/** Tên gợi ý từ tên file: bỏ đuôi, ví dụ `yolov8n.onnx` → `yolov8n`. */
export function nameFromFile(fileName: string): string {
  return fileName.replace(/\.[^.]+$/, '').trim()
}

/** Framework suy từ đuôi file: `.onnx` → onnx, `.safetensors` → torchvision. */
export function frameworkFromFile(fileName: string): 'onnx' | 'torchvision' | null {
  if (/\.onnx$/i.test(fileName)) return 'onnx'
  if (/\.safetensors$/i.test(fileName)) return 'torchvision'
  return null
}

/** Thông tin đọc được trong file weights; trường không có thì `undefined`. */
export interface WeightsMeta {
  architecture?: string
  classNames?: string[]
  inputSize?: number
}

/** Đọc một đoạn byte `[start, end)` của file. */
type Reader = (start: number, end: number) => Promise<Uint8Array>

export function blobReader(blob: Blob): Reader {
  return async (start, end) => new Uint8Array(await blob.slice(start, end).arrayBuffer())
}

const MAX_HEADER = 16 * 1024 * 1024

function parseNames(raw: string): string[] | undefined {
  const text = raw.trim()
  try {
    const json: unknown = JSON.parse(text)
    if (Array.isArray(json) && json.every((n) => typeof n === 'string')) return json
  } catch {
    // Ultralytics ghi `names` dạng dict Python: {0: 'person', 1: 'bicycle'}.
  }
  const pairs = [...text.matchAll(/(\d+)\s*:\s*(['"])(.*?)\2/g)]
  if (pairs.length === 0) return undefined
  return pairs.sort((a, b) => Number(a[1]) - Number(b[1])).map((m) => m[3])
}

function parseSize(raw: string | undefined): number | undefined {
  const value = Number(raw?.match(/\d+/)?.[0])
  return Number.isInteger(value) && value > 0 ? value : undefined
}

function fromProps(props: Record<string, string>): WeightsMeta {
  const names = props.class_names ?? props.names
  const parsed = names ? parseNames(names) : undefined
  return {
    architecture: props.architecture,
    classNames: parsed && uniqueNames(parsed),
    inputSize: parseSize(props.imgsz ?? props.input_size),
  }
}

/** Safetensors: 8 byte độ dài header (u64 LE) rồi header JSON, metadata ở `__metadata__`. */
export async function readSafetensorsMeta(read: Reader): Promise<WeightsMeta> {
  const head = await read(0, 8)
  if (head.length < 8) return {}
  const length = Number(new DataView(head.buffer, head.byteOffset, 8).getBigUint64(0, true))
  if (length <= 0 || length > MAX_HEADER) return {}
  const header: unknown = JSON.parse(new TextDecoder().decode(await read(8, 8 + length)))
  const meta = (header as { __metadata__?: Record<string, string> }).__metadata__
  return meta ? fromProps(meta) : {}
}

/** Varint protobuf tại `pos` của `bytes`; null khi thiếu byte. */
function varint(bytes: Uint8Array, pos: number): [number, number] | null {
  let value = 0
  let scale = 1
  for (let i = pos; i < bytes.length && i < pos + 10; i++) {
    value += (bytes[i] & 0x7f) * scale
    scale *= 128
    if ((bytes[i] & 0x80) === 0) return [value, i + 1]
  }
  return null
}

function decodeEntry(bytes: Uint8Array): [string, string] {
  const text = new TextDecoder()
  let key = ''
  let value = ''
  let pos = 0
  while (pos < bytes.length) {
    const tag = varint(bytes, pos)
    if (!tag) break
    const len = varint(bytes, tag[1])
    if (!len || (tag[0] & 7) !== 2) break
    const chunk = text.decode(bytes.subarray(len[1], len[1] + len[0]))
    if (tag[0] >> 3 === 1) key = chunk
    if (tag[0] >> 3 === 2) value = chunk
    pos = len[1] + len[0]
  }
  return [key, value]
}

/**
 * ONNX (`ModelProto` protobuf): duyệt các field cấp cao, bỏ qua graph theo độ dài, đọc
 * `metadata_props` (field 14, cặp key/value). Không nạp cả file vào bộ nhớ.
 */
export async function readOnnxMeta(read: Reader, size: number): Promise<WeightsMeta> {
  const props: Record<string, string> = {}
  let pos = 0
  for (let fields = 0; pos < size && fields < 10_000; fields++) {
    const head = await read(pos, Math.min(pos + 20, size))
    const tag = varint(head, 0)
    if (!tag) break
    const field = tag[0] >> 3
    const wire = tag[0] & 7
    if (wire === 0) {
      const v = varint(head, tag[1])
      if (!v) break
      pos += v[1]
    } else if (wire === 1) pos += tag[1] + 8
    else if (wire === 5) pos += tag[1] + 4
    else if (wire === 2) {
      const len = varint(head, tag[1])
      if (!len) break
      const start = pos + len[1]
      if (field === 14 && len[0] < MAX_HEADER) {
        const [key, value] = decodeEntry(await read(start, start + len[0]))
        if (key) props[key] = value
      }
      pos = start + len[0]
    } else break
  }
  return fromProps(props)
}

/** Metadata của file weights theo đuôi file; file hỏng hoặc không có metadata → `{}`. */
export async function readWeightsMeta(file: File): Promise<WeightsMeta> {
  try {
    const framework = frameworkFromFile(file.name)
    if (framework === 'torchvision') return await readSafetensorsMeta(blobReader(file))
    if (framework === 'onnx') return await readOnnxMeta(blobReader(file), file.size)
  } catch {
    // Không đọc được metadata: người dùng chọn giá trị như bình thường.
  }
  return {}
}
