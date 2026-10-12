import { describe, expect, it } from 'vitest'

import { listMocks } from '@/api/mocks'
import { boxesOf } from '@/components/case-viewer/boxes'
import type { AttackSpecView, ModelSummary, PrimaryParam, QuickTryView } from '@/contracts/api'

import {
  attackedBoxes,
  cleanBoxes,
  expiryTime,
  imageError,
  levelText,
  levelValue,
  presetLevels,
  QUICK_TRY_MAX_BYTES,
  quickTryAttacks,
  readyModels,
  verdict,
  statusCounts,
} from './logic'

const specs = listMocks<AttackSpecView>('attack_spec')
const completed = listMocks<QuickTryView>('quick_try_view').find((v) => v.status === 'completed')
if (!completed) throw new Error('Thiếu mock quick_try_view completed')
const mixed = completed.levels.find((l) => new Set(l.objects.map((o) => o.status)).size === 3)
if (!mixed) throw new Error('Thiếu level có đủ kept/lost/new')

describe('danh sách attack của thử nhanh', () => {
  it('luôn ẩn patch; ẩn attack cần gradient khi model không có gradient', () => {
    const noGrad = quickTryAttacks(specs, { supports_gradients: false })
    expect(noGrad.some((s) => s.requires_training)).toBe(false)
    expect(noGrad.some((s) => s.requires_gradients)).toBe(false)
    expect(noGrad.length).toBeGreaterThan(0)
    const grad = quickTryAttacks(specs, { supports_gradients: true })
    expect(grad.some((s) => s.requires_training)).toBe(false)
    expect(grad.some((s) => s.requires_gradients)).toBe(true)
  })

  it('chưa chọn model thì coi như không có gradient', () => {
    expect(quickTryAttacks(specs, null).some((s) => s.requires_gradients)).toBe(false)
  })

  it('model chỉ lấy bản ready', () => {
    const models = [{ status: 'ready' }, { status: 'checking' }] as ModelSummary[]
    expect(readyModels(models)).toHaveLength(1)
  })
})

describe('kiểm tra ảnh ở client', () => {
  it('chặn ảnh > 10 MB và định dạng khác JPEG/PNG', () => {
    expect(imageError({ size: 1000, type: 'image/png' })).toBeNull()
    expect(imageError({ size: QUICK_TRY_MAX_BYTES, type: 'image/jpeg' })).toBeNull()
    expect(imageError({ size: QUICK_TRY_MAX_BYTES + 1, type: 'image/png' })).toMatch('10 MB')
    expect(imageError({ size: 10, type: 'image/gif' })).toMatch('JPEG')
  })
})

describe('box theo level (design.md mục 3)', () => {
  it('ảnh sạch: object model thấy trên ảnh sạch, lớp dự đoán ảnh sạch', () => {
    const drawn = boxesOf(cleanBoxes(mixed))
    expect(drawn).toHaveLength(mixed.objects.filter((o) => o.status !== 'new').length)
    expect(new Set(drawn.map((b) => b.kind))).toEqual(new Set(['clean']))
  })

  it('ảnh tấn công: kept → attacked, lost → lost có ×, new → fresh', () => {
    const drawn = boxesOf(attackedBoxes(mixed))
    const kinds = drawn.map((b) => b.kind).sort()
    const expected = mixed.objects
      .map((o) => ({ kept: 'attacked', lost: 'lost', new: 'fresh' })[o.status])
      .sort()
    expect(kinds).toEqual(expected)
    expect(drawn.find((b) => b.kind === 'lost')?.label).toMatch(/^×/)
  })

  it('tắt một lớp thì box của lớp đó không vẽ', () => {
    const layers = { clean: false, attacked: true, lost: false, fresh: true }
    expect(boxesOf(cleanBoxes(mixed, layers))).toHaveLength(0)
    const kinds = boxesOf(attackedBoxes(mixed, layers)).map((b) => b.kind)
    expect(kinds).not.toContain('lost')
    expect(kinds).toContain('fresh')
    expect(kinds).toContain('attacked')
  })

  it('đếm kept/lost/new', () => {
    const counts = statusCounts(mixed)
    expect(counts.kept + counts.lost + counts.new).toBe(mixed.objects.length)
    expect(counts.lost).toBeGreaterThan(0)
  })
})

describe('nhãn', () => {
  it('level: nhãn metadata kèm giá trị, không có thì tham số = giá trị', () => {
    expect(levelText({ level: 8, label: null }, 'eps')).toBe('eps = 8')
    expect(levelText({ level: 2, label: 'Nhẹ' }, 'severity')).toBe('Nhẹ (severity = 2)')
    expect(levelText({ level: 3, label: null })).toBe('3')
  })

  it('giờ xóa dạng HH:MM', () => {
    expect(expiryTime('2026-10-10T08:05:00Z')).toMatch(/^\d{2}:05$/)
  })
})

describe('mức tấn công và kết luận', () => {
  const eps: PrimaryParam = {
    name: 'eps',
    type: 'continuous',
    min: 0,
    max: 32,
    values: null,
    unit: '1/255',
  }
  const severity: PrimaryParam = {
    name: 'severity',
    type: 'discrete',
    min: 1,
    max: 5,
    values: [1, 2, 3, 4, 5],
    unit: 'severity',
  }

  it('level của preset theo cùng công thức backend (rời rạc lấy giá trị gần nhất, không trùng)', () => {
    expect(presetLevels(eps, [0.25, 0.5])).toEqual([8, 16])
    expect(presetLevels(eps, [0.125, 0.25, 0.5, 0.75, 1])).toEqual([4, 8, 16, 24, 32])
    expect(presetLevels(severity, [0.5, 0.0625, 0.125, 0.25])).toEqual([1, 2, 3])
    expect(levelValue(8, '1/255')).toBe('8/255')
    expect(levelValue(3, 'severity')).toBe('3')
  })

  it('kết luận: giữ đủ, không detect được, detect nhầm, không có vật thể', () => {
    expect(verdict({ kept: 3, lost: 0, new: 0 })).toEqual({
      tone: 'pass',
      text: 'Model vẫn nhận ra đủ 3 vật thể, không phát hiện nhầm.',
    })
    expect(verdict({ kept: 1, lost: 2, new: 1 })).toEqual({
      tone: 'fail',
      text: 'Model không detect được 2/3 vật thể, detect nhầm 1 vật thể không có trên ảnh sạch.',
    })
    expect(verdict({ kept: 2, lost: 0, new: 1 }).text).toBe(
      'Model detect nhầm 1 vật thể không có trên ảnh sạch.',
    )
    expect(verdict({ kept: 0, lost: 0, new: 0 }).tone).toBe('neutral')
  })
})
