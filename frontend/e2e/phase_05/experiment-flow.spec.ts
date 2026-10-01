// validation.md Phase 5, Frontend E2E: wizard → chi tiết → tiến độ → kết quả, failure case, tái lập.
import { expect, test } from '@playwright/test'

import { activeUser, expectNoHorizontalScroll, loginUi } from '../phase_04/helpers'
import { addLevel, attackCard, visibleButton, WORKER_TIMEOUT } from './helpers'

test('engineer đi hết wizard, theo dõi tới khi xong, xem kết quả, failure case và tái lập', async ({
  page,
  request,
}, info) => {
  test.setTimeout(WORKER_TIMEOUT + 120_000)
  const email = await activeUser(request, info, ['engineer'])
  await loginUi(page, email)
  await page.goto('/experiments/new')
  const next = () => visibleButton(page, /^Tiếp/).click()

  // Bước 1–3.
  await page.getByRole('radio', { name: /dev-open/ }).click()
  await next()
  await page.getByRole('radio', { name: /yolov8n-coco/ }).click()
  await next()
  await page.getByRole('radiogroup', { name: 'Dataset version' }).getByRole('radio').first().click()
  await page
    .getByRole('radiogroup', { name: 'Slice' })
    .getByRole('radio', { name: /5 ảnh/ })
    .click()
  await expect(page.getByText('Tự chọn mapping duy nhất')).toBeVisible()
  await next()

  // Bước 4: FGSM eps 4, PGD eps 4.
  for (const label of ['fgsm v1', 'pgd_linf v1']) {
    await page.getByLabel(label, { exact: true }).check()
    await addLevel(attackCard(page, label), '4')
  }
  if (info.project.name === 'phone') {
    // Điện thoại: một bước một màn hình, thanh dưới hiển thị thời gian ước lượng.
    await expect(page.getByTestId('uoc-luong-thanh-duoi')).toBeVisible()
    await expect(page.getByText('Bước 4/6')).toBeVisible()
  }
  await expectNoHorizontalScroll(page)
  await next()

  // Bước 5: local-dev chọn sẵn (worker của E2E đang online).
  await expect(page.getByRole('radio', { name: /local-dev/ })).toHaveAttribute(
    'aria-checked',
    'true',
  )
  await next()

  // Bước 6: thấy ước lượng, xác nhận.
  await expect(page.getByText('Ước lượng từng run')).toBeVisible()
  await expect(page.locator('dt:text-is("Seed") + dd').filter({ visible: true })).toHaveText('0')
  await visibleButton(page, /^Chạy/).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByRole('button', { name: 'Chạy experiment' }).click()
  await expect(page).toHaveURL(/\/experiments\/[0-9a-f-]{36}$/)
  const detailUrl = page.url()

  // Tiến độ cập nhật không cần tải lại (polling 2 giây) tới khi xong. Viewport chạy sau dùng cùng
  // cấu hình nên run trúng cache ("bỏ qua"), vẫn có metric và failure case của run gốc.
  await expect(
    page.locator('[data-kind="experiment"][data-status="completed"]').first(),
  ).toBeVisible({ timeout: WORKER_TIMEOUT })
  await expect(page.getByText(/2\/2 hoàn thành|0\/2 hoàn thành, 2 bỏ qua/).first()).toBeVisible()
  expect(page.url()).toBe(detailUrl)
  await expectNoHorizontalScroll(page)

  // Kết quả: biểu đồ và bảng.
  await page.getByRole('tab', { name: 'Kết quả' }).click()
  await expect(page.getByText('Số liệu của fgsm')).toBeAttached()
  await expect(page.locator('svg.recharts-surface').first()).toBeVisible()

  // Chi phí: thời gian đã dùng so với giới hạn.
  await page.getByRole('tab', { name: 'Chi phí' }).click()
  await expect(
    page.getByText(/Thời gian xử lý đã dùng: .+ \/ giới hạn \d+ (giờ|phút)/),
  ).toBeVisible()

  // Failure case: thumbnail có watermark; mở một case, bật tắt lớp box.
  await page.getByRole('tab', { name: 'Failure case' }).click()
  await expect(
    page.getByText(/BẢN NHÁP – CHƯA DUYỆT: kết quả chưa được reviewer duyệt/),
  ).toBeVisible()
  const firstCase = page.locator('a[href^="/failure-cases/"]').first()
  await expect(firstCase).toBeVisible()
  await firstCase.click()
  await expect(page).toHaveURL(/\/failure-cases\//)
  // Phase 6: worker làm mờ mọi case mới nên case hiển thị bình thường dù DEV_ALLOW_UNBLURRED bật
  // (requirements.md Phase 6, mục Làm mờ); dải cảnh báo dev chỉ còn cho case cũ chưa làm mờ.
  await expect(page.locator('[data-display-mode="normal"]')).toBeVisible()
  await expect(page.getByText('Chưa làm mờ – chỉ dùng cho phát triển')).toHaveCount(0)
  const groundTruth = page.getByRole('button', { name: 'Ground truth' })
  await expect(groundTruth).toHaveAttribute('aria-pressed', 'true')
  await groundTruth.click()
  await expect(groundTruth).toHaveAttribute('aria-pressed', 'false')
  if (info.project.name === 'phone') {
    await expect(page.getByLabel('Kéo để so sánh ảnh sạch và ảnh sau tấn công')).toBeVisible()
  }
  await expectNoHorizontalScroll(page)

  // Tái lập: fingerprint và tải manifest.
  await page.goto(`${detailUrl}?tab=repro`)
  await expect(page.getByRole('button', { name: 'Copy fingerprint' }).first()).toBeVisible()
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Tải manifest.json' }).first().click()
  expect((await download).suggestedFilename()).toMatch(/^manifest-[0-9a-f-]{36}\.json$/)
})
