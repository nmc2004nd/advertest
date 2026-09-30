import { describe, expect, it } from 'vitest'

import { listMocks } from '@/api/mocks'
import type { CaseDetections, FailureCaseView } from '@/contracts/api'

import { canvasSize, hitTest, iou, lostObjects, toCss } from './geometry'

describe('hình học box', () => {
  it('IoU', () => {
    expect(iou([0, 0, 10, 10], [0, 0, 10, 10])).toBe(1)
    expect(iou([0, 0, 10, 10], [5, 0, 15, 10])).toBeCloseTo(1 / 3)
    expect(iou([0, 0, 10, 10], [20, 20, 30, 30])).toBe(0)
  })

  it('object bị mất: phát hiện đúng trên ảnh sạch, mất sau tấn công', () => {
    const view = listMocks<FailureCaseView>('failure_case_view')[0]
    // Mock: 3 GT đều được phát hiện trên ảnh sạch; sau tấn công chỉ còn một box sai chỗ.
    expect(lostObjects(view.detections)).toEqual([0, 1, 2])
    const kept: CaseDetections = {
      ...view.detections,
      attacked: [view.detections.clean[0]],
    }
    expect(lostObjects(kept)).toEqual([1, 2])
    const missedOnClean: CaseDetections = { ...view.detections, clean: [] }
    expect(lostObjects(missedOnClean)).toEqual([]) // không phát hiện từ đầu: không tính là mất
  })

  it('canvas theo devicePixelRatio', () => {
    expect(canvasSize(320, 320, 3)).toEqual({ width: 960, height: 960, ratio: 3 })
    expect(canvasSize(320, 320, 0)).toEqual({ width: 320, height: 320, ratio: 1 })
  })

  it('đổi tọa độ ảnh 640 sang khung CSS', () => {
    expect(toCss([64, 128, 320, 640], 320)).toEqual([32, 64, 160, 320])
  })

  it('chạm vào box: chọn box nhỏ nhất chứa điểm', () => {
    const big = { bbox: [0, 0, 100, 100] as const, id: 'lon' }
    const small = { bbox: [10, 10, 20, 20] as const, id: 'nho' }
    expect(hitTest([big, small], 15, 15)?.id).toBe('nho')
    expect(hitTest([big, small], 50, 50)?.id).toBe('lon')
    expect(hitTest([big, small], 150, 50)).toBeNull()
  })
})
