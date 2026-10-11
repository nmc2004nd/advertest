import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import { listMocks } from '@/api/mocks'
import type { DisplayMode, FailureCaseView } from '@/contracts/api'

import { BOX_COLORS, BOX_STROKE, boxesOf } from './boxes'
import { BLURRED_TEXT, CaseViewer, DEV_WARNING, HIDDEN_TEXT, WATERMARK } from './CaseViewer'
import { THIRD_IMAGE_LABEL } from './labels'

/** Case kiểu Phase 5 (chưa làm mờ, ảnh thứ ba là nhiễu khuếch đại) theo display_mode. */
function view(mode: DisplayMode): FailureCaseView {
  const found = listMocks<FailureCaseView>('failure_case_view').find(
    (v) =>
      v.display_mode === mode && !v.anonymization && (mode !== 'normal' || v.urls.clean !== null),
  )
  if (!found) throw new Error(`Thiếu mock ${mode}`)
  return found
}

const render = (mode: DisplayMode) => renderToStaticMarkup(<CaseViewer caseView={view(mode)} />)

describe('CaseViewer (validation.md Frontend unit)', () => {
  it('hidden_unanonymized: khung giữ chỗ, không có thẻ ảnh, vẫn có lớp box', () => {
    const html = render('hidden_unanonymized')
    expect(html).toContain(HIDDEN_TEXT)
    expect(html).not.toContain('<img')
    expect(html).toContain('<canvas')
    expect(html).not.toContain(DEV_WARNING)
  })

  it('dev_unblurred: có ảnh và dải cảnh báo', () => {
    const html = render('dev_unblurred')
    expect(html).toContain(DEV_WARNING)
    expect(html).toContain('role="alert"')
    expect(html).toContain('<img')
  })

  it('normal: ảnh qua URL tạm thời, không cảnh báo, không khung giữ chỗ', () => {
    const html = render('normal')
    const clean = view('normal').urls.clean
    expect(html).toContain(`src="${clean}"`)
    expect(html).not.toContain(DEV_WARNING)
    expect(html).not.toContain(HIDDEN_TEXT)
  })

  it.each<DisplayMode>(['normal', 'hidden_unanonymized', 'dev_unblurred'])(
    'watermark luôn hiển thị (%s)',
    (mode) => {
      expect(render(mode)).toContain(WATERMARK)
    },
  )

  it('có nút bật tắt từng lớp box, slider cho điện thoại và ảnh nhiễu', () => {
    const html = render('normal')
    for (const label of [
      'Ground truth',
      'Dự đoán ảnh sạch',
      'Dự đoán sau tấn công',
      'Vùng bỏ qua',
    ]) {
      expect(html).toContain(label)
    }
    expect(html.match(/aria-pressed="true"/g)).toHaveLength(4)
    expect(html).toContain('type="range"')
    expect(html).toContain('Nhiễu khuếch đại')
  })

  it('box của object bị mất có nhãn riêng', () => {
    const detections = view('normal').detections
    const boxes = boxesOf({
      groundTruth: detections.ground_truth,
      predictions: detections.attacked,
      predictionKind: 'attacked',
      ignoreRegions: detections.ignore_regions,
      lost: [0],
    })
    expect(boxes.filter((b) => b.kind === 'lost').map((b) => b.label)).toEqual(['× car (bị mất)'])
    expect(boxes).toHaveLength(
      detections.ground_truth.length +
        detections.attacked.length +
        detections.ignore_regions.length,
    )
  })

  it('có chỗ cho form verdict của Phase 8; không có form thì không chừa cột', () => {
    const html = renderToStaticMarkup(
      <CaseViewer caseView={view('normal')} aside={<form data-verdict="phase8" />} />,
    )
    expect(html).toContain('data-verdict="phase8"')
    expect(html).toContain('lg:grid-cols-')
    expect(render('normal')).not.toContain('lg:grid-cols-')
  })
})

describe('CaseViewer Phase 6 (task 34)', () => {
  const views = listMocks<FailureCaseView>('failure_case_view')

  it('case đã làm mờ: dải "Đã làm mờ mặt và biển số"; case cũ thì không', () => {
    const blurred = views.filter((v) => v.anonymization?.applied)
    expect(blurred.length).toBeGreaterThan(0)
    for (const v of blurred) {
      expect(renderToStaticMarkup(<CaseViewer caseView={v} />)).toContain(BLURRED_TEXT)
    }
    const old = views.find((v) => !v.anonymization)
    if (!old) throw new Error('Thiếu mock case cũ')
    expect(renderToStaticMarkup(<CaseViewer caseView={old} />)).not.toContain(BLURRED_TEXT)
  })

  it('nhãn ảnh thứ ba theo loại', () => {
    for (const kind of ['amplified_noise', 'difference', 'patch_location'] as const) {
      const v = views.find((x) => (x.perturbation_kind ?? 'amplified_noise') === kind)
      if (!v) throw new Error(`Thiếu mock ${kind}`)
      const html = renderToStaticMarkup(<CaseViewer caseView={v} />)
      expect(html).toContain(
        `<figcaption class="text-sm font-medium">${THIRD_IMAGE_LABEL[kind]}</figcaption>`,
      )
      for (const other of Object.values(THIRD_IMAGE_LABEL)) {
        if (other !== THIRD_IMAGE_LABEL[kind]) expect(html).not.toContain(other)
      }
    }
  })
})

describe('Trình vẽ box Phase R3 (design.md mục 3)', () => {
  const detections = listMocks<FailureCaseView>('failure_case_view')[0].detections

  it('kiểu nét: ground truth đứt 8-4, phát hiện sai mới đứt 3-3, object bị mất liền dày 3', () => {
    expect(BOX_STROKE.ground_truth).toEqual({ width: 2, dash: [8, 4] })
    expect(BOX_STROKE.fresh).toEqual({ width: 2, dash: [3, 3] })
    expect(BOX_STROKE.lost).toEqual({ width: 3, dash: [] })
    expect(BOX_STROKE.ignore_regions.dash).toEqual([4, 3])
    expect(BOX_COLORS.fresh).toBe('#f97316')
  })

  it('dự đoán thuộc `fresh` vẽ ở lớp phát hiện sai mới, phần còn lại giữ lớp sau tấn công', () => {
    if (detections.attacked.length === 0) throw new Error('Mock thiếu dự đoán sau tấn công')
    const boxes = boxesOf({
      groundTruth: [],
      predictions: detections.attacked,
      predictionKind: 'attacked',
      ignoreRegions: [],
      lost: [],
      fresh: [0],
    })
    expect(boxes.map((b) => b.kind)).toEqual([
      'fresh',
      ...detections.attacked.slice(1).map(() => 'attacked'),
    ])
    expect(boxes[0].label).toContain('(mới)')
  })

  it('chú thích lớp: ô màu ground truth nét đứt, object bị mất có ký hiệu ×', () => {
    const html = renderToStaticMarkup(
      <CaseViewer caseView={listMocks<FailureCaseView>('failure_case_view')[0]} />,
    )
    expect(html).toMatch(/data-swatch="ground_truth"[^>]*border-style:dashed/)
    expect(html).toContain('× Object bị mất')
  })
})
