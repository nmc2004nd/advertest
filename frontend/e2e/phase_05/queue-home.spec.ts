// validation.md Phase 5, Frontend E2E: khối engineer trên /home; gửi experiment thứ 4 khi đã có
// 3 experiment đang chờ → thông báo queue_limit_reached. Ba experiment gửi tới máy `e2e-offline`
// (không có worker) nên nằm chờ. Phase R3 (plan.md task 23a): lần gửi thứ 4 qua wizard 3 bước.
import { expect, test } from '@playwright/test'

import { activeUser, loginUi } from '../phase_04/helpers'
import { keepAttacks, wizardToAttacks } from '../phase_r3/helpers'
import { cancelExperiment, createExperiment, visibleButton } from './helpers'

test('/home có khối experiment đang chờ; experiment thứ 4 bị chặn với queue_limit_reached', async ({
  page,
  request,
}, info) => {
  test.setTimeout(120_000) // 4 lần tạo và 3 lần hủy qua API, chậm khi worker CPU bận
  const email = await activeUser(request, info, ['engineer'])
  await loginUi(page, email)
  const ids: string[] = []
  for (let i = 0; i < 3; i++) ids.push(await createExperiment(page, [['fgsm', [4]]], 'e2e-offline'))

  try {
    await page.goto('/home')
    await expect(
      page.getByRole('link', { name: 'Tạo experiment' }).filter({ visible: true }).first(),
    ).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Đang chạy hoặc chờ' })).toBeVisible()
    for (const id of ids) {
      const item = page.locator(`a[href="/experiments/${id}"]`)
      await expect(item).toBeVisible()
      await expect(item.locator('[data-kind="experiment"][data-status="queued"]')).toBeVisible()
    }

    // Lần gửi thứ 4 qua wizard (máy local-dev được chọn sẵn).
    await page
      .getByRole('link', { name: 'Tạo experiment' })
      .filter({ visible: true })
      .first()
      .click()
    await expect(page).toHaveURL(/\/experiments\/new$/)
    await wizardToAttacks(page)
    await keepAttacks(page, { fgsm: [4] })
    await visibleButton(page, 'Tạo experiment').click()
    await expect(page.getByText(/Bạn đã có 3 experiment đang chờ/)).toBeVisible()
    await expect(page).toHaveURL(/\/experiments\/new$/)
    await expect(page.getByRole('heading', { name: 'Attack và xác nhận' })).toBeVisible()
  } finally {
    for (const id of ids) await cancelExperiment(page, id)
  }
})
