// validation.md Phase 8, Frontend E2E (backend, worker CPU thật, fixture 5 ảnh của scripts/e2e.sh):
// - trọn luồng: reviewer tạo protocol → engineer tạo experiment theo protocol (attack điền sẵn) →
//   chạy xong → gửi duyệt → reviewer nhận, review case bắt buộc bằng phím tắt (desktop, tablet) hoặc
//   vuốt và bottom sheet (điện thoại), chấp nhận → report `ready` → tải PDF → `/verify/:id` chọn file
//   vừa tải → "Khớp"; sửa 1 byte → "Không khớp"; chọn file không phát request nào mang nội dung file;
// - luồng yêu cầu sửa → engineer thấy quyết định và "Nhân bản để sửa" → wizard mở với cấu hình cũ;
// - engineer không thấy nút tải report; trang report có "BẢN CHÍNH THỨC";
// - người có cả role engineer và reviewer không thấy experiment của mình trong hàng đợi;
// - không trang nào của phase cuộn ngang (390px trên điện thoại).
import { readFile } from 'node:fs/promises'

import { expect, type Page, test } from '@playwright/test'

import { expectNoHorizontalScroll } from '../phase_04/helpers'
import { visibleButton } from '../phase_05/helpers'
import {
  APPROVE,
  claimApi,
  createExperimentApi,
  createProtocolApi,
  decideApi,
  LEVELS,
  readyReportId,
  reviewAllApi,
  submitApi,
  swipe,
  userPage,
  waitStatus,
  WORKER_TIMEOUT,
} from './helpers'

async function createProtocolUi(page: Page, name: string, levels: [number, number]) {
  await page.goto('/protocols')
  await visibleButton(page, 'Tạo protocol').click()
  await page.getByLabel('Tên protocol').fill(name)
  await page.getByLabel('Mục đích').fill('Kiểm thử E2E Phase 8: FGSM quét lưới')
  await page.getByLabel('Kích thước slice tối thiểu').fill('5')
  await page.getByLabel('Số case bắt buộc review mỗi attack').fill('2')
  // Worker E2E chạy từ working tree của máy dev (có thể có thay đổi chưa commit).
  await page.getByLabel('Không chấp nhận run chạy từ code chưa commit').uncheck()
  await page.locator('#attack-0-ten').selectOption('fgsm')
  await page.locator('#attack-0-level').fill(levels.join(', '))
  await page.locator('#tieu-chi-0-attack').selectOption('fgsm')
  await page.locator('#tieu-chi-0-level').fill(String(levels[1]))
  await page.locator('#tieu-chi-0-nguong').fill('95')
  await expectNoHorizontalScroll(page)
  await page.locator('form').getByRole('button', { name: 'Tạo protocol' }).click()
  await expect(page.getByText(name)).toBeVisible()
  await expectNoHorizontalScroll(page)
}

async function createExperimentUi(page: Page, protocol: string): Promise<string> {
  const next = () => visibleButton(page, /^Tiếp/).click()
  await page.goto('/experiments/new')
  await page.getByRole('radiogroup', { name: 'Protocol' }).getByText(protocol).click()
  await expect(page.getByTestId('protocol-chi-tiet')).toBeVisible()
  await next()
  await page.getByRole('radio', { name: /yolov8n-coco/ }).click()
  await next()
  await page.getByRole('radiogroup', { name: 'Dataset version' }).getByRole('radio').first().click()
  await page
    .getByRole('radiogroup', { name: 'Slice' })
    .getByRole('radio', { name: /5 ảnh/ })
    .click()
  await next()
  // Bước 4: attack bắt buộc đã được thêm và khóa theo protocol.
  const fgsm = page.getByRole('checkbox', { name: 'fgsm v1 Theo protocol' })
  await expect(fgsm).toBeChecked()
  await expect(fgsm).toBeDisabled()
  await next()
  await next()
  await visibleButton(page, /^Chạy/).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Chạy experiment' }).click()
  await expect(page).toHaveURL(/\/experiments\/[0-9a-f-]{36}$/)
  return page.url().split('/').pop() ?? ''
}

async function reviewCasesWithKeyboard(page: Page, count: number) {
  for (let i = 0; i < count; i++) {
    await expect(page.getByText(`Case bắt buộc ${i + 1}/${count}`)).toBeVisible()
    await page.keyboard.press('?')
    await expect(page.getByTestId('bang-phim-tat')).toBeVisible()
    await page.keyboard.press('Escape')
    await page.keyboard.press('3') // Nhỏ
    await page.keyboard.press('a') // Chấp nhận được
    await page.keyboard.press('Control+Enter')
    await expect(page.getByTestId('lich-su-verdict')).toContainText('v1: Nhỏ, Chấp nhận được')
    if (i < count - 1) await page.keyboard.press('j')
  }
}

async function reviewCasesOnPhone(page: Page, count: number) {
  for (let i = 0; i < count; i++) {
    await expect(page.getByText(`Case bắt buộc ${i + 1}/${count}`)).toBeVisible()
    await page.getByRole('button', { name: 'Ghi verdict' }).click()
    const sheet = page.getByRole('dialog')
    await sheet
      .getByRole('radiogroup', { name: 'Mức nghiêm trọng' })
      .getByRole('radio', { name: /Nhỏ/ })
      .click()
    await sheet
      .getByRole('radiogroup', { name: 'Loại verdict' })
      .getByRole('radio', { name: /Lỗi nhãn/ })
      .click()
    await sheet.getByRole('button', { name: /Lưu verdict/ }).click()
    await expect(sheet).toBeHidden()
    await expect(page.getByTestId('lich-su-verdict')).toContainText('v1: Nhỏ, Lỗi nhãn')
    await expectNoHorizontalScroll(page)
    if (i < count - 1) await swipe(page, 'left')
  }
}

test('trọn luồng: protocol → experiment → gửi duyệt → review → chấp nhận → report → xác minh', async ({
  browser,
}, info) => {
  test.setTimeout(WORKER_TIMEOUT + 300_000)
  const levels = LEVELS[info.project.name]
  const reviewer = await userPage(browser, info, ['reviewer'])
  const engineer = await userPage(browser, info, ['engineer'])
  const protocol = `e2e-p8-ui-${info.project.name}-${Date.now()}`

  // 1. Reviewer tạo protocol bằng form.
  await createProtocolUi(reviewer.page, protocol, levels)

  // 2. Engineer tạo experiment theo protocol bằng wizard, chờ chạy xong, gửi duyệt.
  const experimentId = await createExperimentUi(engineer.page, protocol)
  await expect(
    engineer.page.locator('[data-kind="experiment"][data-status="completed"]').first(),
  ).toBeVisible({ timeout: WORKER_TIMEOUT })
  await visibleButton(engineer.page, 'Gửi duyệt').click()
  await engineer.page.getByRole('dialog').getByRole('button', { name: 'Gửi duyệt' }).click()
  await expect(engineer.page.getByText(/Đã khóa/).first()).toBeVisible()

  // 3. Reviewer nhận review, ghi verdict cho mọi case bắt buộc.
  const page = reviewer.page
  await page.goto('/reviews')
  await expectNoHorizontalScroll(page)
  await page.locator(`a[href="/reviews/${experimentId}"]`).filter({ visible: true }).first().click()
  await expect(page).toHaveURL(new RegExp(`/reviews/${experimentId}$`))
  await page.getByRole('button', { name: 'Nhận review' }).click()
  await expect(page.getByRole('button', { name: 'Trả lại' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Chấp nhận' })).toBeDisabled()
  await expect(page.getByTestId('ly-do-khoa')).toContainText('Mọi case bắt buộc đã có verdict')
  await expectNoHorizontalScroll(page)
  const caseLinks = page.locator(`a[href^="/reviews/${experimentId}/cases/"]`)
  const count = await caseLinks.count()
  expect(count).toBeGreaterThan(0)
  await caseLinks.first().click()
  await expect(page).toHaveURL(/\/cases\//)
  await expectNoHorizontalScroll(page)
  if (info.project.name === 'phone') await reviewCasesOnPhone(page, count)
  else await reviewCasesWithKeyboard(page, count)

  // 4. Khung quyết định: đủ điều kiện thì "Chấp nhận" mở khóa.
  await page.goto(`/reviews/${experimentId}`)
  await expect(page.getByText(`${count}/${count} đã review`)).toBeVisible()
  await page.getByLabel('Kết luận', { exact: true }).fill(APPROVE.conclusion)
  await page.getByLabel('Biện pháp khắc phục').fill(APPROVE.mitigation)
  await page.getByLabel('Kết luận về model').selectOption('meets_criteria')
  await expect(page.getByRole('button', { name: 'Chấp nhận' })).toBeEnabled()
  await expectNoHorizontalScroll(page)
  await page.getByRole('button', { name: 'Chấp nhận' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Chấp nhận' }).click()
  await expect(page.getByRole('dialog')).toBeHidden()

  // 5. Report ready (sinh nền); reviewer tải PDF.
  const reportId = await readyReportId(page, experimentId)
  await page.goto(`/reports/${reportId}`)
  await expect(page.getByTestId('dai-chinh-thuc')).toContainText('BẢN CHÍNH THỨC')
  await expectNoHorizontalScroll(page)
  const downloading = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Tải PDF' }).click()
  const download = await downloading
  expect(download.suggestedFilename()).toMatch(/\.pdf$/)
  const pdf = await readFile(await download.path())

  // 6. Xác minh: chọn file → "Khớp"; không request nào mang nội dung file.
  const anonymous = await browser.newContext({
    baseURL: info.project.use.baseURL,
    viewport: info.project.use.viewport,
  })
  const verify = await anonymous.newPage()
  await verify.goto(`/verify/${reportId}`)
  await expect(verify.getByText(reportId).first()).toBeVisible()
  await expectNoHorizontalScroll(verify)
  const sent: (string | null)[] = []
  verify.on('request', (request) => sent.push(request.postData()))
  await verify
    .getByLabel('Chọn file PDF hoặc JSON của report')
    .setInputFiles({ name: 'report.pdf', mimeType: 'application/pdf', buffer: pdf })
  await expect(verify.getByTestId('ket-qua-xac-minh')).toContainText('Khớp')
  await expect(verify.getByTestId('ket-qua-xac-minh')).not.toContainText('Không khớp')
  expect(sent.filter((body) => body !== null && body.length > 0)).toEqual([])

  // Sửa 1 byte → "Không khớp".
  const tampered = Buffer.from(pdf)
  tampered[Math.floor(tampered.length / 2)] ^= 0x01
  await verify
    .getByLabel('Chọn file PDF hoặc JSON của report')
    .setInputFiles({ name: 'sua.pdf', mimeType: 'application/pdf', buffer: tampered })
  await expect(verify.getByTestId('ket-qua-xac-minh')).toContainText('Không khớp')
  await expectNoHorizontalScroll(verify)
  await anonymous.close()
})

test('yêu cầu sửa: engineer thấy quyết định và "Nhân bản để sửa" mở wizard với cấu hình cũ', async ({
  browser,
}, info) => {
  test.setTimeout(WORKER_TIMEOUT + 120_000)
  const levels = LEVELS[info.project.name]
  const reviewer = await userPage(browser, info, ['reviewer'])
  const engineer = await userPage(browser, info, ['engineer'])
  const protocol = await createProtocolApi(reviewer.page, levels)
  const experimentId = await createExperimentApi(engineer.page, protocol.id, levels)
  await waitStatus(engineer.page, experimentId, 'completed')
  await submitApi(engineer.page, experimentId)
  await claimApi(reviewer.page, experimentId)

  const page = reviewer.page
  await page.goto(`/reviews/${experimentId}`)
  await page.getByLabel('Kết luận', { exact: true }).fill('Thiếu level eps 8; chạy lại')
  await page.getByRole('button', { name: 'Yêu cầu sửa' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Yêu cầu sửa' }).click()
  await expect(page.getByRole('dialog')).toBeHidden()

  const mine = engineer.page
  await mine.goto(`/experiments/${experimentId}?tab=review`)
  await expect(mine.getByTestId('quyet-dinh')).toContainText('Yêu cầu sửa')
  await expect(mine.getByTestId('quyet-dinh')).toContainText('Thiếu level eps 8')
  await mine
    .getByRole('link', { name: 'Nhân bản để sửa' })
    .filter({ visible: true })
    .first()
    .click()
  await expect(mine).toHaveURL(new RegExp(`/experiments/new\\?clone=${experimentId}$`))
  await expect(mine.getByRole('heading', { name: 'Xác nhận' })).toBeVisible()
  await expect(mine.getByText(`fgsm: ${levels.join(', ')}`).first()).toBeAttached()
  await expectNoHorizontalScroll(mine)
})

test('engineer không thấy nút tải report; trang report có "BẢN CHÍNH THỨC"', async ({
  browser,
}, info) => {
  test.setTimeout(WORKER_TIMEOUT + 180_000)
  const levels = LEVELS[info.project.name]
  const reviewer = await userPage(browser, info, ['reviewer'])
  const engineer = await userPage(browser, info, ['engineer'])
  const protocol = await createProtocolApi(reviewer.page, levels)
  const experimentId = await createExperimentApi(engineer.page, protocol.id, levels)
  await waitStatus(engineer.page, experimentId, 'completed')
  await submitApi(engineer.page, experimentId)
  await claimApi(reviewer.page, experimentId)
  await reviewAllApi(reviewer.page, experimentId)
  await decideApi(reviewer.page, experimentId, APPROVE)
  const reportId = await readyReportId(engineer.page, experimentId)

  const page = engineer.page
  await page.goto(`/experiments/${experimentId}?tab=review`)
  await page.getByRole('link', { name: 'Report chính thức' }).click()
  await expect(page).toHaveURL(new RegExp(`/reports/${reportId}$`))
  await expect(page.getByTestId('dai-chinh-thuc')).toContainText('BẢN CHÍNH THỨC')
  await expect(page.getByRole('button', { name: 'Tải PDF' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Tải JSON' })).toHaveCount(0)
  await expectNoHorizontalScroll(page)
  await page.goto('/reports')
  await expect(
    page.locator(`a[href="/reports/${reportId}"]`).filter({ visible: true }).first(),
  ).toBeVisible()
  await expectNoHorizontalScroll(page)
})

test('người có cả role engineer và reviewer không thấy experiment của mình trong hàng đợi', async ({
  browser,
}, info) => {
  test.setTimeout(WORKER_TIMEOUT + 120_000)
  const levels = LEVELS[info.project.name]
  const other = await userPage(browser, info, ['reviewer'])
  const both = await userPage(browser, info, ['engineer', 'reviewer'])
  const protocol = await createProtocolApi(other.page, levels)
  const experimentId = await createExperimentApi(both.page, protocol.id, levels)
  await waitStatus(both.page, experimentId, 'completed')
  await submitApi(both.page, experimentId)

  await both.page.goto('/reviews?status=waiting')
  await expect(both.page.getByRole('tab', { name: 'Chờ nhận' })).toHaveAttribute(
    'aria-selected',
    'true',
  )
  await expect(both.page.locator(`a[href="/reviews/${experimentId}"]`)).toHaveCount(0)
  await expectNoHorizontalScroll(both.page)
  await other.page.goto('/reviews?status=waiting')
  await expect(other.page.locator(`a[href="/reviews/${experimentId}"]`).first()).toBeAttached()
  // Vào thẳng trang review experiment của mình: không có nút nhận, có lời giải thích.
  await both.page.goto(`/reviews/${experimentId}`)
  await expect(both.page.getByRole('button', { name: 'Nhận review' })).toHaveCount(0)
  await expect(both.page.getByText('không được review experiment do mình tạo')).toBeVisible()
})
