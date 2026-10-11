import { describe, expect, it } from 'vitest'

import { MODEL_UPLOAD_MAX_BYTES, parseClassNames, weightsFileError } from './model-file'

describe('weightsFileError (validation.md Group 6: chặn ở client)', () => {
  it('nhận .onnx và .safetensors tới 500 MB', () => {
    expect(weightsFileError({ name: 'yolo.onnx', size: 10 })).toBeNull()
    expect(weightsFileError({ name: 'frcnn.SAFETENSORS', size: MODEL_UPLOAD_MAX_BYTES })).toBeNull()
  })

  it('chặn .pt, pickle, đuôi khác; lời nhắn nêu .onnx', () => {
    for (const name of ['model.pt', 'model.pth', 'model.pkl', 'model.onnx.pt', 'onnx']) {
      expect(weightsFileError({ name, size: 10 })).toContain('.onnx')
    }
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
