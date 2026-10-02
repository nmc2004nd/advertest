/** Phase 8 (plan task 32, 33): trang report, nút tải theo quyền, trang xác minh và hash. */
import { Route, Routes } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { listMocks } from '@/api/mocks'
import type { ExperimentDetail, ReportDetail, ReportView, VerifyInfo } from '@/contracts/api'
import { experimentKey } from '@/features/experiments/api'
import { ExperimentDetailPage } from '@/features/experiments/ExperimentDetailPage'
import { expectLabelledControls, render } from '@/test-utils'

import { REPORTS_KEY, reportKey, verifyKey } from './api'
import { compareHash, hasWebCrypto, sha256Hex, verifyFile } from './hash'
import { OFFICIAL } from './labels'
import { ReportPage } from './ReportPage'
import { ReportsPage } from './ReportsPage'
import { VerifyPage, VerifyPanel } from './VerifyPage'

const views = listMocks<ReportView>('report_view')
const details = listMocks<ReportDetail>('report_detail')
const info = listMocks<VerifyInfo>('verify_info')[0]
const ready = details.find((d) => d.report.status === 'ready')
const failed = details.find((d) => d.report.status === 'failed')
const generating = views.find((v) => v.status === 'generating')
if (!ready || !failed || !generating || !info) throw new Error('Thiếu mock report')

/** "File mẫu": vài KB byte cố định giả lập PDF. */
const sample = new TextEncoder().encode(`%PDF-1.7\n${'Báo cáo AdverTest\n'.repeat(300)}%%EOF\n`)
/** SHA-256 của `sample`, tính độc lập bằng Python `hashlib` (không dùng code đang được kiểm). */
const SAMPLE_SHA256 = '6d2dadaecb32fe7e6dfb6a6db7b9579fbc7cd15c03b29ee2702a77e9a559adc6'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('hash trong trình duyệt', () => {
  it('Trang xác minh tính SHA-256 đúng trên file mẫu, và không gửi request nào chứa nội dung file', async () => {
    const fetchSpy = vi.fn(() => Promise.reject(new Error('mạng bị chặn trong test')))
    vi.stubGlobal('fetch', fetchSpy)
    expect(hasWebCrypto()).toBe(true)
    // Vector chuẩn FIPS 180-2.
    expect(await sha256Hex(new TextEncoder().encode('abc'))).toBe(
      'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad',
    )
    const issued = { ...info, pdf_sha256: SAMPLE_SHA256 }
    const file = new Blob([sample], { type: 'application/pdf' })
    const { hash, result } = await verifyFile(file, issued)
    expect(hash).toBe(SAMPLE_SHA256)
    expect(result).toEqual({ match: true, format: 'pdf' })
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('sửa 1 byte → "Không khớp"; so hash không phân biệt hoa thường; khớp JSON', async () => {
    const issued = { ...info, pdf_sha256: SAMPLE_SHA256.toUpperCase() }
    const tampered = sample.slice()
    tampered[10] ^= 0x01
    expect((await verifyFile(new Blob([tampered]), issued)).result).toEqual({ match: false })
    expect((await verifyFile(new Blob([sample]), issued)).result).toEqual({
      match: true,
      format: 'pdf',
    })
    expect(compareHash(info.json_sha256, info)).toEqual({ match: true, format: 'json' })
  })
})

describe('trang xác minh', () => {
  it('công khai: mã report, ngày, hai hash, ô chọn file có nhãn', () => {
    const html = render(
      <Routes>
        <Route path="/verify/:id" element={<VerifyPage />} />
      </Routes>,
      `/verify/${info.report_id}`,
      undefined,
      [[verifyKey(info.report_id), info]],
    )
    for (const text of [info.report_id, info.pdf_sha256, info.json_sha256, 'Xác minh report']) {
      expect(html).toContain(text)
    }
    expect(html).toContain('type="file"')
    expect(html).toContain('file không được gửi đi đâu')
    expectLabelledControls(html, 1)
  })

  it('không có Web Crypto (không phải HTTPS): báo cần HTTPS, không có ô chọn file', () => {
    const html = render(<VerifyPanel info={info} webCrypto={false} />)
    expect(html).toContain('HTTPS')
    expect(html).not.toContain('type="file"')
  })

  it('hiện "Khớp" hoặc "Không khớp" kèm hash vừa tính', () => {
    const match = render(
      <VerifyPanel
        info={info}
        initial={{
          fileName: 'report.pdf',
          hash: info.pdf_sha256,
          result: { match: true, format: 'pdf' },
        }}
      />,
    )
    expect(match).toContain('Khớp')
    expect(match).not.toContain('Không khớp')
    const mismatch = render(
      <VerifyPanel
        info={info}
        initial={{ fileName: 'sua.pdf', hash: 'ab'.repeat(32), result: { match: false } }}
      />,
    )
    expect(mismatch).toContain('Không khớp')
    expect(mismatch).toContain('ab'.repeat(32))
  })
})

function reportPage(detail: ReportDetail, me: string) {
  return render(
    <Routes>
      <Route path="/reports/:id" element={<ReportPage />} />
    </Routes>,
    `/reports/${detail.report.id}`,
    me,
    [[reportKey(detail.report.id), detail]],
  )
}

describe('trang report', () => {
  it('report sẵn sàng: "BẢN CHÍNH THỨC", mã report, link xác minh, đủ 9 mục', () => {
    const html = reportPage(ready, 'reviewer')
    expect(html).toContain(OFFICIAL)
    expect(html).toContain(ready.report.id)
    expect(html).toContain(`/verify/${ready.report.id}`)
    for (const title of [
      '1. Tóm tắt',
      '2. Phạm vi và lưu ý bắt buộc',
      '3. Cấu hình',
      '4. Kết quả',
      '5. Toàn bộ run',
      '6. Failure case đã review',
      '7. Lịch sử',
      '8. Tái lập',
      '9. Tài nguyên',
    ]) {
      expect(html).toContain(title)
    }
    const snapshot = ready.snapshot
    if (!snapshot) throw new Error('mock ready thiếu snapshot')
    for (const note of snapshot.notes) expect(html).toContain(note.text)
    for (const run of snapshot.runs) expect(html).toContain(run.attack_spec_name)
    expect(html).toContain(snapshot.summary.conclusion)
  })

  it('reviewer (report.export) thấy nút tải; engineer và admin không thấy', () => {
    expect(reportPage(ready, 'reviewer')).toContain('Tải PDF')
    for (const me of ['engineer', 'admin']) {
      const html = reportPage(ready, me)
      expect(html).toContain(OFFICIAL)
      expect(html).not.toContain('Tải PDF')
      expect(html).not.toContain('Tải JSON')
    }
  })

  it('report lỗi: reviewer có "Sinh lại", engineer không; không có dải chính thức', () => {
    const reviewer = reportPage(failed, 'reviewer')
    expect(reviewer).toContain('Sinh lại')
    expect(reviewer).not.toContain(OFFICIAL)
    expect(reportPage(failed, 'engineer')).not.toContain('Sinh lại')
  })

  it('report đang sinh: báo đang sinh, chưa có nội dung', () => {
    const html = reportPage({ report: generating, snapshot: null }, 'reviewer')
    expect(html).toContain('đang được sinh')
    expect(html).not.toContain('1. Tóm tắt')
  })
})

describe('danh sách report và link từ experiment', () => {
  it('bảng desktop, thẻ điện thoại, trạng thái', () => {
    const html = render(<ReportsPage />, '/reports', 'engineer', [[REPORTS_KEY, views]])
    expect(html).toContain('<table')
    expect(html).toContain('xl:hidden')
    for (const v of views) expect(html).toContain(`/reports/${v.id}`)
    expect(html).toContain('Sinh lỗi')
    expect(html).toContain('Đang sinh')
  })

  it('tab Review của experiment đã chấp nhận có link tới report', () => {
    const glob = import.meta.glob<ExperimentDetail>(
      '../../../../contracts/mocks/experiment_detail/review_approved_report_ready.json',
      { eager: true, import: 'default' },
    )
    const detail = Object.values(glob)[0]
    const report = detail.report
    if (!report) throw new Error('mock thiếu report')
    const html = render(
      <Routes>
        <Route path="/experiments/:id" element={<ExperimentDetailPage />} />
      </Routes>,
      `/experiments/${detail.id}?tab=review`,
      'engineer',
      [
        [experimentKey(detail.id), detail],
        [[...experimentKey(detail.id), 'runs'], []],
      ],
    )
    expect(html).toContain('link-report')
    expect(html).toContain(`/reports/${report.id}`)
  })
})
