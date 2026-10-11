import { describe, expect, it } from 'vitest'

import { listMocks } from '@/api/mocks'
import { boxesOf } from '@/components/case-viewer/boxes'
import type { AttackSpecView, ModelSummary, QuickTryView } from '@/contracts/api'

import {
  attackedBoxes,
  cleanBoxes,
  expiryTime,
  imageError,
  levelText,
  QUICK_TRY_MAX_BYTES,
  quickTryAttacks,
  readyModels,
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
