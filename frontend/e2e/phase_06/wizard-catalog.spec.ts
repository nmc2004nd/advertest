// validation.md Phase 6, Frontend E2E (wizard): nháp v1 cũ không làm hỏng wizard; preset "Toàn bộ
// catalog" chọn đủ 10 attack, adv_patch 0.1 và 0.25; chưa chọn slice huấn luyện thì không sang
// bước tiếp; danh sách slice huấn luyện không có slice giao slice đánh giá; công tắc dừng sớm bật
// mặc định; ước lượng có thời gian train patch.
import { expect, test } from '@playwright/test'

import { activeUser, expectNoHorizontalScroll, loginUi } from '../phase_04/helpers'
import { attackCard, visibleButton } from '../phase_05/helpers'
import { createPhase06Experiment, RUN_TIMEOUT, waitCompleted } from './helpers'

test('wizard: preset toàn catalog, slice huấn luyện, dừng sớm, thời gian train', async ({
  page,
  request,
}, info) => {
  test.setTimeout(RUN_TIMEOUT + 120_000)
  const email = await activeUser(request, info, ['engineer'])
  await loginUi(page, email)
  // Máy local-dev cần cost profile của adv_patch (có sec_per_image_iteration) để ước lượng phần
  // train: một experiment patch nhỏ cho worker đo (khóa patch khác 0.1, 0.25 nên preset vẫn cần train).
  await waitCompleted(page, await createPhase06Experiment(page, [['adv_patch', [0.03]]]))

  // Nháp của wizard cũ (khóa v1) trong sessionStorage.
  await page.addInitScript(() => {
    sessionStorage.setItem(
      'advertest.wizard.v1',
      JSON.stringify({ step: 4, attacks: [{ attackSpecId: 'cu' }] }),
    )
  })
  await page.goto('/experiments/new')
  await expect(page.getByRole('heading', { name: 'Protocol' })).toBeVisible()
  const next = () => visibleButton(page, /^Tiếp/).click()

  await page.getByRole('radio', { name: /dev-open/ }).click()
  await next()
  await page.getByRole('radio', { name: /yolov8n-coco/ }).click()
  await next()
  await page.getByRole('radiogroup', { name: 'Dataset version' }).getByRole('radio').first().click()
  await page
    .getByRole('radiogroup', { name: 'Slice' })
    .getByRole('radio', { name: /3 ảnh/ })
    .click()
  await expect(page.getByText('Tự chọn mapping duy nhất')).toBeVisible()
  await next()

  // Bước 4.
  await expect(page.getByRole('heading', { name: 'Tấn công', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Biến đổi điều kiện' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Che khuất' })).toBeVisible()
  await expect(page.getByRole('switch', { name: 'Dừng sớm khi model đã sụp' })).toBeChecked()
  await page.getByRole('button', { name: 'Toàn bộ catalog' }).click()
  const boxes = page.locator('div.rounded-lg.border input[type="checkbox"]:not([role="switch"])')
  await expect(boxes).toHaveCount(10)
  for (const box of await boxes.all()) await expect(box).toBeChecked()

  const patch = attackCard(page, 'adv_patch v2')
  await expect(patch.getByText('0.1', { exact: true })).toBeVisible()
  await expect(patch.getByText('0.25', { exact: true })).toBeVisible()
  // Chưa chọn slice huấn luyện: không sang bước tiếp.
  await expect(visibleButton(page, /^Tiếp/)).toBeDisabled()
  const training = page.getByRole('radiogroup', { name: /Slice huấn luyện/ })
  await expect(training.getByRole('radio')).toHaveCount(1) // chỉ slice 2 ảnh (không giao)
  await expect(training.getByRole('radio')).toContainText('2 ảnh')
  await training.getByRole('radio').click()
  await expect(visibleButton(page, /^Tiếp/)).toBeEnabled()
  await expect(page.getByTestId('thoi-gian-train')).toContainText('Thời gian train:')
  await expectNoHorizontalScroll(page)
})
