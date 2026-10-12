import { describe, expect, it } from 'vitest'

import {
  effectiveMapping,
  KITTI_COCO,
  mappedCount,
  mappingError,
  suggestMapping,
} from './class-mapping'

const KITTI = Object.keys(KITTI_COCO)

describe('gợi ý class mapping', () => {
  it('model COCO: gợi ý đúng preset kitti-coco', () => {
    expect(suggestMapping(KITTI, ['person', 'bicycle', 'car', 'truck'])).toEqual(KITTI_COCO)
  })

  it('preset không có class đích trong model thì bỏ; class khác lấy theo tên trùng', () => {
    const suggested = suggestMapping(['Car', 'Truck', 'Bus'], ['Car', 'bus'])
    expect(suggested).toEqual({ Car: 'Car', Truck: null, Bus: 'bus' })
  })

  it('lựa chọn của người dùng đè gợi ý, bỏ lựa chọn không còn trong model', () => {
    const suggested = { Car: 'car', Van: 'car' }
    const merged = effectiveMapping(suggested, { Van: null, Car: 'xe', Tram: 'car' }, ['car'])
    expect(merged).toEqual({ Car: 'car', Van: null })
  })

  it('cần ít nhất một class được map', () => {
    expect(mappingError({ Car: null })).not.toBeNull()
    expect(mappingError({})).not.toBeNull()
    expect(mappingError({ Car: 'car', Tram: null })).toBeNull()
    expect(mappedCount(KITTI_COCO)).toBe(5)
  })
})
