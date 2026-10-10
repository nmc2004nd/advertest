// validation.md Phase R3, Group 4 — Trang chủ "việc cần làm" theo vai trò (M6):
// - người chưa có việc: "Không có việc cần làm" và hành động gợi ý;
// - engineer có experiment Khám phá đã xong: việc `promote_ready` dẫn tới experiment;
// - admin có tài khoản chờ duyệt: việc `user_pending`.
import { expect, test } from '@playwright/test'

import { requestAccessApi, uniqueEmail } from '../phase_04/helpers'
import { userPage, waitStatus } from '../phase_08/helpers'
import { experimentApi, WORKER_TIMEOUT } from './helpers'

test.setTimeout(WORKER_TIMEOUT + 60_000)

test('engineer mới: không có việc, gợi ý tạo experiment Khám phá', async ({ browser }, info) => {
  const { page } = await userPage(browser, info, ['engineer'])
  await page.goto('/home')
  await expect(page.getByText('Không có việc cần làm')).toBeVisible()
  await expect(
    page.getByRole('link', { name: 'Tạo experiment Khám phá' }).filter({ visible: true }),
  ).toBeVisible()
})

test('engineer: experiment Khám phá đã xong là việc "nâng lên chính thức"', async ({
  browser,
}, info) => {
  const { page } = await userPage(browser, info, ['engineer'])
  const id = await experimentApi(page, [2])
  await waitStatus(page, id, 'completed')
  await page.goto('/home')
  const item = page
    .getByTestId('todo-list')
    .locator('[data-testid="todo-item"][data-kind="promote_ready"]')
  await expect(item).toBeVisible()
  await expect(item).toContainText('1')
  await item.getByRole('link').first().click()
  await expect(page).toHaveURL(new RegExp(`/experiments/${id}`))
})

test('admin: tài khoản chờ duyệt là việc cần làm', async ({ browser, request }, info) => {
  await requestAccessApi(request, uniqueEmail(info, 'r3-home'))
  const { page } = await userPage(browser, info, ['admin'])
  await page.goto('/home')
  const item = page
    .getByTestId('todo-list')
    .locator('[data-testid="todo-item"][data-kind="user_pending"]')
  await expect(item).toBeVisible()
})
