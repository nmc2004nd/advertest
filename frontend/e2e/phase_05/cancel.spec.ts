// validation.md Phase 5, Frontend E2E: hủy experiment đang chạy qua hộp xác nhận.
import { expect, test } from '@playwright/test'

import { activeUser, loginUi } from '../phase_04/helpers'
import { createExperiment, WORKER_TIMEOUT } from './helpers'

test('hủy experiment đang chạy qua hộp xác nhận → trạng thái cancelled', async ({
  page,
  request,
}, info) => {
  test.setTimeout(WORKER_TIMEOUT + 60_000)
  const email = await activeUser(request, info, ['engineer'])
  await loginUi(page, email)
  // 12 level PGD lệch ngẫu nhiên: không trúng cache, đủ lâu để còn đang chạy khi bấm hủy.
  const offset = Math.round(Math.random() * 900) / 1000
  const levels = Array.from({ length: 12 }, (_, i) => Number((i + 1 + offset).toFixed(3)))
  const id = await createExperiment(page, [['pgd_linf', levels]])
  await page.goto(`/experiments/${id}`)
  await expect(page.locator('[data-kind="experiment"][data-status="running"]').first()).toBeVisible(
    { timeout: WORKER_TIMEOUT },
  )
  await page.getByRole('button', { name: 'Hủy experiment' }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog).toContainText('Không hoàn tác được')
  await dialog.getByRole('button', { name: 'Hủy experiment' }).click()
  await expect(
    page.locator('[data-kind="experiment"][data-status="cancelled"]').first(),
  ).toBeVisible()
  await expect(page.getByRole('button', { name: 'Hủy experiment' })).toHaveCount(0)
})
