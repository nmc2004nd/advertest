// validation.md Phase R3, Group 7 — Thử nhanh (M8), worker công cụ thật:
// - danh sách attack không có patch;
// - chạy fog trên ảnh KITTI fixture: nhãn "Không phải kết quả kiểm thử" kèm giờ xóa;
// - kéo thanh trượt level: ảnh tấn công và bảng object đổi, không có request mới tới API thử nhanh;
// - không cuộn ngang.
import { fileURLToPath } from 'node:url'

import { expect, test } from '@playwright/test'

import { expectNoHorizontalScroll } from '../phase_04/helpers'
import { visibleButton } from '../phase_05/helpers'
import { userPage } from '../phase_08/helpers'
import { chooseOption, countRequests, WORKER_TIMEOUT } from './helpers'

const IMAGE = fileURLToPath(
  new URL('../../../tests/fixtures/kitti/image_2/000902.png', import.meta.url),
)

test.setTimeout(WORKER_TIMEOUT + 60_000)

test('thử nhanh fog, kéo thanh trượt level', async ({ browser }, info) => {
  const { page } = await userPage(browser, info, ['engineer'])
  await page.goto('/quick-try')
  await chooseOption(page, 'Model', 'yolov8n-coco')
  // Kiểu tấn công là lưới thẻ (radio) hiện sẵn, không phải ô chọn.
  const attackGroup = page.getByRole('radiogroup', { name: 'Attack' })
  const attacks = await attackGroup
    .getByRole('radio')
    .evaluateAll((els) => els.map((el) => el.getAttribute('data-attack') ?? ''))
  expect(attacks).not.toContain('adv_patch')
  await attackGroup.locator('[data-attack="fog"]').click()
  await expect(page.getByTestId('preset-levels').first()).toBeVisible()
  await page.getByLabel('Ảnh', { exact: true }).setInputFiles(IMAGE)
  await visibleButton(page, 'Chạy thử nhanh').click()

  const result = page.getByTestId('quick-try-result')
  await expect(result).toBeVisible({ timeout: WORKER_TIMEOUT })
  await expect(page.getByTestId('not-a-test-result')).toContainText('Không phải kết quả kiểm thử')
  await expect(page.getByTestId('not-a-test-result')).toContainText(/\d{1,2}:\d{2}/)
  await expect(page.getByTestId('object-table')).toBeVisible()
  await expect(page.getByTestId('quick-try-verdict')).toContainText('Model')
  await expectNoHorizontalScroll(page)

  const attacked = page.getByTestId('attacked-image')
  const before = await attacked.getAttribute('src')
  const requests = countRequests(page, /\/api\/quick-tries/)
  const slider = page.getByRole('slider', { name: 'Level' })
  await slider.focus()
  await page.keyboard.press('ArrowRight')
  await expect(attacked).not.toHaveAttribute('src', before ?? '')
  await expect(page.getByTestId('object-table')).toBeVisible()
  expect(requests()).toBe(0)
})
