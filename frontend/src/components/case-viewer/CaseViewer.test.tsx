import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import { listMocks } from '@/api/mocks'
import type { DisplayMode, FailureCaseView } from '@/contracts/api'

import { boxesOf } from './boxes'
import { CaseViewer, DEV_WARNING, HIDDEN_TEXT, WATERMARK } from './CaseViewer'

function view(mode: DisplayMode): FailureCaseView {
  const found = listMocks<FailureCaseView>('failure_case_view').find(
    (v) => v.display_mode === mode && (mode !== 'normal' || v.urls.clean !== null),
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
    expect(boxes.filter((b) => b.kind === 'lost').map((b) => b.label)).toEqual(['car (bị mất)'])
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
