// validation.md Phase R3, Group 6 — Admin catalog và duyệt spec (M7), worker công cụ thật:
// - admin tạo biến thể corruption từ spec có sẵn → thấy "Đang kiểm tra" rồi kết quả 7 mục →
//   reviewer khác kích hoạt (hộp xác nhận) → spec có trong wizard của engineer;
// - người tạo spec có cả role reviewer: nút kích hoạt bị vô hiệu kèm lý do;
// - từ chối phải có lý do.
import { expect, type Page, test } from '@playwright/test'

import { visibleButton } from '../phase_05/helpers'
import { userPage } from '../phase_08/helpers'
import { chooseOption, getJson, WORKER_TIMEOUT } from './helpers'

test.setTimeout(WORKER_TIMEOUT + 120_000)

function uniqueName(prefix: string): string {
  return `${prefix}_${Date.now().toString(36)}${Math.floor(Math.random() * 1e4)}`
}

/** Tạo biến thể của `snow` qua giao diện; chờ kiểm tra xong (`Chờ duyệt`). */
async function createVariant(page: Page, name: string): Promise<void> {
  await page.goto('/admin/attacks')
  await visibleButton(page, 'Tạo attack spec').click()
  await chooseOption(page, 'Sao chép từ', 'snow')
  await page.getByLabel('Tên spec', { exact: true }).fill(name)
  await page.getByLabel('Tên hiển thị', { exact: true }).fill(`Tuyết ${name}`)
  await page.getByLabel('Mô tả', { exact: true }).fill('Biến thể tuyết cho kiểm thử E2E Phase R3.')
  await visibleButton(page, 'Tạo spec').click()
  await expect(page.getByTestId('spec-status')).toHaveText(/Đang kiểm tra|Chờ duyệt/)
  await expect(page.getByTestId('spec-status')).toHaveText(/Chờ duyệt/, {
    timeout: WORKER_TIMEOUT,
  })
  await expect(page.getByTestId('check-item')).toHaveCount(7)
}

function pendingRow(page: Page, name: string) {
  return page.getByTestId('pending-spec').filter({ hasText: name })
}

test('tạo, kiểm tra, kích hoạt rồi dùng trong wizard', async ({ browser }, info) => {
  const name = uniqueName('snow_e2e')
  const admin = await userPage(browser, info, ['admin'])
  await createVariant(admin.page, name)

  const reviewer = await userPage(browser, info, ['reviewer'])
  await reviewer.page.goto('/attack-specs/pending')
  await pendingRow(reviewer.page, name).getByRole('button', { name: 'Kích hoạt' }).click()
  const dialog = reviewer.page.getByRole('dialog')
  await expect(dialog).toBeVisible()
  await dialog.getByRole('button', { name: 'Kích hoạt' }).click()
  await expect(pendingRow(reviewer.page, name)).toHaveCount(0)

  const engineer = await userPage(browser, info, ['engineer'])
  const specs = await getJson<{ name: string }[]>(engineer.page, '/attack-specs')
  expect(specs.map((s) => s.name)).toContain(name)
})

test('người tạo không tự kích hoạt; từ chối cần lý do', async ({ browser }, info) => {
  const name = uniqueName('snow_self')
  const creator = await userPage(browser, info, ['admin', 'reviewer'])
  await createVariant(creator.page, name)
  await creator.page.goto('/attack-specs/pending')
  const own = pendingRow(creator.page, name)
  await expect(own.getByRole('button', { name: 'Kích hoạt' })).toBeDisabled()
  await expect(own).toContainText('Bạn đã tạo spec này')

  const reviewer = await userPage(browser, info, ['reviewer'])
  await reviewer.page.goto('/attack-specs/pending')
  await pendingRow(reviewer.page, name).getByRole('button', { name: 'Từ chối' }).click()
  const dialog = reviewer.page.getByRole('dialog')
  await expect(dialog.getByRole('button', { name: 'Từ chối' })).toBeDisabled()
  await dialog.getByLabel('Lý do').fill('Severity 3 trùng với spec snow đang dùng.')
  await expect(dialog.getByRole('button', { name: 'Từ chối' })).toBeEnabled()
  await dialog.getByRole('button', { name: 'Từ chối' }).click()
  await expect(pendingRow(reviewer.page, name)).toHaveCount(0)
})
