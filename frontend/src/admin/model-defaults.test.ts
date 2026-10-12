/** Đọc metadata file weights khi đăng ký model, bộ class và giá trị mặc định. */
import { describe, expect, it } from 'vitest'

import {
  COCO80,
  COCO91_TORCHVISION,
  frameworkFromFile,
  nameFromFile,
  readOnnxMeta,
  readSafetensorsMeta,
  uniqueNames,
} from './model-defaults'

const reader = (bytes: Uint8Array) => async (start: number, end: number) => bytes.slice(start, end)

function safetensors(metadata: Record<string, string>): Uint8Array {
  const header = new TextEncoder().encode(JSON.stringify({ __metadata__: metadata }))
  const out = new Uint8Array(8 + header.length + 16)
  new DataView(out.buffer).setBigUint64(0, BigInt(header.length), true)
  out.set(header, 8)
  return out
}

/** Protobuf tối thiểu: varint, field LEN. */
const varint = (n: number): number[] => {
  const out: number[] = []
  do {
    out.push((n & 0x7f) | (n >= 0x80 ? 0x80 : 0))
    n = Math.floor(n / 128)
  } while (n > 0)
  return out
}
const len = (field: number, body: number[]) => [
  ...varint((field << 3) | 2),
  ...varint(body.length),
  ...body,
]
const str = (field: number, text: string) => len(field, [...new TextEncoder().encode(text)])

function onnx(props: Record<string, string>): Uint8Array {
  const graph = new Array(5000).fill(7) // graph lớn, bỏ qua theo độ dài
  return new Uint8Array([
    ...varint((1 << 3) | 0), ...varint(8), // ir_version
    ...str(2, 'pytorch'),
    ...len(7, graph),
    ...Object.entries(props).flatMap(([k, v]) => len(14, [...str(1, k), ...str(2, v)])),
  ]) // prettier-ignore
}

describe('đọc metadata file weights', () => {
  it('safetensors torchvision: kiến trúc và class trong __metadata__', async () => {
    const bytes = safetensors({
      architecture: 'fcos_resnet50_fpn',
      class_names: JSON.stringify(['__background__', 'N/A', 'car', 'N/A']),
    })
    expect(await readSafetensorsMeta(reader(bytes))).toEqual({
      architecture: 'fcos_resnet50_fpn',
      // Tên trùng (N/A của COCO torchvision) thêm index: contract không nhận class trùng.
      classNames: ['__background__', 'N/A_1', 'car', 'N/A_3'],
      inputSize: undefined,
    })
  })

  it('ONNX: class_names JSON, hoặc names dạng dict Python của Ultralytics kèm imgsz', async () => {
    const json = onnx({ class_names: JSON.stringify(['person', 'car']) })
    expect((await readOnnxMeta(reader(json), json.length)).classNames).toEqual(['person', 'car'])
    const ultra = onnx({
      names: "{1: 'car', 0: 'person', 2: \"traffic light\"}",
      imgsz: '[640, 640]',
    })
    expect(await readOnnxMeta(reader(ultra), ultra.length)).toEqual({
      architecture: undefined,
      classNames: ['person', 'car', 'traffic light'],
      inputSize: 640,
    })
  })

  it('safetensors Ultralytics (export-safetensors): framework, kiến trúc, names JSON, imgsz', async () => {
    const bytes = safetensors({
      framework: 'ultralytics',
      architecture: 'yolo11n',
      names: JSON.stringify(['person', 'car']),
      imgsz: '640',
    })
    const meta = await readSafetensorsMeta(reader(bytes))
    expect(meta).toEqual({
      framework: 'ultralytics',
      architecture: 'yolo11n',
      classNames: ['person', 'car'],
      inputSize: 640,
    })
    expect(frameworkFromFile('yolo11n.safetensors', meta)).toBe('ultralytics')
  })

  it('file không có metadata hoặc hỏng → không có gì', async () => {
    const empty = onnx({})
    expect((await readOnnxMeta(reader(empty), empty.length)).classNames).toBeUndefined()
    expect(await readSafetensorsMeta(reader(new Uint8Array(4)))).toEqual({})
  })
})

describe('giá trị mặc định', () => {
  it('tên và framework theo file', () => {
    expect(nameFromFile('yolov8n.onnx')).toBe('yolov8n')
    expect(frameworkFromFile('m.SAFETENSORS')).toBe('torchvision')
    expect(frameworkFromFile('m.onnx')).toBe('onnx')
    expect(frameworkFromFile('m.pt')).toBeNull()
    // Kiến trúc YOLO Ultralytics trong metadata cũng đủ để nhận ra.
    expect(frameworkFromFile('m.safetensors', { architecture: 'yolov9t' })).toBe('ultralytics')
    expect(frameworkFromFile('m.safetensors', { architecture: 'fcos_resnet50_fpn' })).toBe(
      'torchvision',
    )
  })

  it('bộ class COCO: 80 cho YOLO, 91 cho torchvision, không trùng tên (contract)', () => {
    expect(COCO80).toHaveLength(80)
    expect(COCO91_TORCHVISION).toHaveLength(91)
    expect(new Set(COCO91_TORCHVISION).size).toBe(91)
    expect(COCO91_TORCHVISION[12]).toBe('N/A_12')
    expect(uniqueNames(['a', 'b', 'a'])).toEqual(['a_0', 'b', 'a_2'])
  })
})
