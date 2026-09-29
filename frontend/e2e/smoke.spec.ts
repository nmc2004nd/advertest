// Kịch bản khói (Phase 4 Group 0, task 4b): bản build phục vụ được, proxy /api tới backend thật,
// không cuộn ngang ở cả 3 viewport. Kịch bản của từng phase nằm trong e2e/phase_NN/.
import { expect, test } from '@playwright/test'

test('trang chủ tải được và không cuộn ngang', async ({ page }) => {
  await page.goto('/')
  await expect(page.locator('#root')).not.toBeEmpty()
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - window.innerWidth,
  )
  expect(overflow).toBeLessThanOrEqual(0)
})

test('API thật trả lời qua proxy /api', async ({ request }) => {
  const response = await request.get('/api/health')
  expect(response.status()).toBe(200)
  const body = await response.json()
  expect(body.postgres.ok).toBe(true)
})
