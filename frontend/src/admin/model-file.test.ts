import { describe, expect, it } from 'vitest'

import {
  guessConvertFramework,
  MODEL_UPLOAD_MAX_BYTES,
  needsConversion,
  parseClassNames,
  weightsFileError,
} from './model-file'

describe('weightsFileError (validation.md Group 6: chặn ở client)', () => {
  it('nhận .onnx và .safetensors tới 500 MB', () => {
    expect(weightsFileError({ name: 'yolo.onnx', size: 10 })).toBeNull()
    expect(weightsFileError({ name: 'frcnn.SAFETENSORS', size: MODEL_UPLOAD_MAX_BYTES })).toBeNull()
  })

  it('chặn pickle và đuôi khác; lời nhắn nêu .onnx', () => {
    for (const name of ['model.pkl', 'model.ckpt', 'model.pt.zip', 'onnx']) {
      expect(weightsFileError({ name, size: 10 })).toContain('.onnx')
    }
  })

  it('.pt/.pth nhận được nhưng phải chuyển đổi (đề xuất contract 003)', () => {
    for (const name of ['best.pt', 'frcnn.PTH']) {
      expect(weightsFileError({ name, size: 10 })).toBeNull()
      expect(needsConversion(name)).toBe(true)
    }
    expect(needsConversion('m.safetensors')).toBe(false)
    expect(guessConvertFramework('frcnn.pth')).toBe('torchvision')
    expect(guessConvertFramework('best.pt')).toBe('ultralytics')
  })

  it('chặn file lớn hơn 500 MB và file rỗng', () => {
    expect(weightsFileError({ name: 'a.onnx', size: MODEL_UPLOAD_MAX_BYTES + 1 })).toContain(
      '500 MB',
    )
    expect(weightsFileError({ name: 'a.onnx', size: 0 })).not.toBeNull()
  })
})

describe('parseClassNames', () => {
  it('theo dòng hoặc dấu phẩy, giữ thứ tự', () => {
    expect(parseClassNames('person\ncar, bicycle\n\n')).toEqual(['person', 'car', 'bicycle'])
  })

  it('rỗng hoặc trùng thì lỗi', () => {
    expect(parseClassNames(' \n')).toBeInstanceOf(Error)
    expect(parseClassNames('car, car')).toBeInstanceOf(Error)
  })
})
