// validation.md Phase 6, Frontend E2E: experiment toàn catalog (level rút gọn) chạy xong trên
// fixture; tab Kết quả có bảng xếp hạng, biểu đồ cột, trục chuẩn hóa; trình xem case có dải "Đã làm
// mờ" và nhãn ảnh thứ ba theo loại; 390px hiển thị thẻ, không cuộn ngang.
import { expect, test } from '@playwright/test'

import { activeUser, expectNoHorizontalScroll, loginUi } from '../phase_04/helpers'
import { createPhase06Experiment, REDUCED_CATALOG, RUN_TIMEOUT, waitCompleted } from './helpers'

test('toàn catalog: xếp hạng, biểu đồ cột, trục chuẩn hóa, case đã làm mờ', async ({
  page,
  request,
}, info) => {
  test.setTimeout(RUN_TIMEOUT + 120_000)
  const email = await activeUser(request, info, ['engineer'])
  await loginUi(page, email)
  const id = await createPhase06Experiment(page, REDUCED_CATALOG)
  await waitCompleted(page, id)

  await page.goto(`/experiments/${id}?tab=results`)
  await expect(page.getByRole('heading', { name: 'Xếp hạng attack' })).toBeVisible()
  await expect(page.getByText('Diện tích mức sụt (auc_drop) theo attack')).toBeVisible()
  if (info.project.name === 'phone') {
    // Điện thoại: bảng xếp hạng dạng thẻ (bảng ẩn dưới md).
    const cards = page.getByRole('list', { name: 'Bảng xếp hạng attack' })
    await expect(cards).toBeVisible()
    await expect(cards.getByRole('listitem')).toHaveCount(REDUCED_CATALOG.length)
  } else {
    const table = page.getByRole('table', { name: 'Bảng xếp hạng attack' })
    await expect(table).toBeVisible()
    await expect(table.locator('tbody tr')).toHaveCount(REDUCED_CATALOG.length)
  }
  await expectNoHorizontalScroll(page)

  // Trục hoành chuẩn hóa: bật thì bảng số liệu có cột % dải, mọi giá trị trong 0–100%.
  const toggle = page.getByRole('switch', { name: /Trục hoành chuẩn hóa/ })
  await expect(toggle).not.toBeChecked()
  await toggle.check()
  await expect(page.getByRole('columnheader', { name: '% dải' })).toHaveCount(
    REDUCED_CATALOG.length,
  )
  // Cột thứ hai của mỗi bảng số liệu là % dải.
  const percents = await page
    .locator('table', { has: page.getByRole('columnheader', { name: '% dải' }) })
    .locator('tbody tr td:nth-child(2)')
    .allInnerTexts()
  expect(percents.length).toBeGreaterThanOrEqual(2 * REDUCED_CATALOG.length)
  for (const text of percents) {
    expect(text).toMatch(/^\d+(\.\d)?%$/)
    const value = Number(text.replace('%', ''))
    expect(value).toBeGreaterThanOrEqual(0)
    expect(value).toBeLessThanOrEqual(100)
  }
  await expectNoHorizontalScroll(page)

  // Case của corruption: đã làm mờ, ảnh thứ ba là vùng khác biệt.
  await page.goto(`/experiments/${id}?tab=cases`)
  const fog = page.locator('section', { has: page.getByRole('heading', { name: /^fog · / }) })
  await fog.locator('a[href^="/failure-cases/"]').first().click()
  await expect(page).toHaveURL(/\/failure-cases\//)
  await expect(page.getByText('Đã làm mờ mặt và biển số')).toBeVisible()
  await expect(page.locator('figcaption', { hasText: 'Vùng khác biệt' })).toBeVisible()
  await expect(page.getByText('Chưa làm mờ – chỉ dùng cho phát triển')).toHaveCount(0)
  await expectNoHorizontalScroll(page)
})
