// validation.md Phase 5, Frontend E2E: wizard → chi tiết → tiến độ → kết quả, failure case, tái lập.
// Phase R3 (plan.md task 23a): đi qua wizard 3 bước; Chi phí và Tái lập là section của Tổng quan.
import { expect, test } from '@playwright/test'

import { activeUser, expectNoHorizontalScroll, loginUi } from '../phase_04/helpers'
import { keepAttacks, selectedOption, wizardToAttacks } from '../phase_r3/helpers'
import { visibleButton, WORKER_TIMEOUT } from './helpers'

test('engineer đi hết wizard, theo dõi tới khi xong, xem kết quả, failure case và tái lập', async ({
  page,
  request,
}, info) => {
  test.setTimeout(WORKER_TIMEOUT + 120_000)
  const email = await activeUser(request, info, ['engineer'])
  await loginUi(page, email)
  // Bước 1–2 (wizard 3 bước, Phase R3): Khám phá, preset Nhanh, model, slice 5 ảnh. Máy local-dev
  // chọn sẵn (worker của E2E đang online).
  await wizardToAttacks(page, {
    beforeNext: async () => {
      await expect(page.getByText('Tự chọn class mapping duy nhất')).toBeVisible()
      await expect(selectedOption(page, 'Máy chạy')).toHaveText(/local-dev/)
    },
  })

  // Bước 3: chỉ FGSM eps 4, PGD eps 4.
  await keepAttacks(page, { fgsm: [4], pgd_linf: [4] })
  if (info.project.name === 'phone') {
    // Điện thoại: một bước một màn hình, thanh dưới hiển thị thời gian ước lượng.
    await expect(page.getByTestId('uoc-luong-thanh-duoi')).toBeVisible()
    await expect(page.getByText('Bước 3 trên 3')).toBeVisible()
  }
  await expectNoHorizontalScroll(page)

  // Thấy ước lượng, tạo experiment.
  await expect(page.getByText('Ước lượng từng run')).toBeVisible()
  await expect(page.locator('dt:text-is("Seed") + dd').filter({ visible: true })).toHaveText('0')
  await visibleButton(page, 'Tạo experiment').click()
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

  // Chi phí (Phase R3: section trong Tổng quan): thời gian đã dùng so với giới hạn.
  await page.getByRole('tab', { name: 'Tổng quan' }).click()
  await page.getByRole('button', { name: 'Chi phí' }).click()
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
