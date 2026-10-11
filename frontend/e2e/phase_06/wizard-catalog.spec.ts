// validation.md Phase 6, Frontend E2E (wizard): nháp v1 cũ không làm hỏng wizard; đủ 10 attack,
// adv_patch 0.1 và 0.25; chưa chọn slice huấn luyện thì chưa thêm được patch; danh sách slice huấn
// luyện không có slice giao slice đánh giá; công tắc dừng sớm bật mặc định; ước lượng có thời gian
// train patch. Phase R3 (plan.md task 23a): wizard 3 bước, không còn preset "Toàn bộ catalog"
// (bản nháp Khám phá gồm cả catalog trừ spec cần train; patch thêm bằng chip).
import { expect, test } from '@playwright/test'

import { activeUser, expectNoHorizontalScroll, loginUi } from '../phase_04/helpers'
import { visibleButton } from '../phase_05/helpers'
import { attackRow, getJson, setLevels, wizardToAttacks } from '../phase_r3/helpers'
import { createPhase06Experiment, RUN_TIMEOUT, waitCompleted } from './helpers'

test('wizard: cả catalog, slice huấn luyện, dừng sớm, thời gian train', async ({
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
  await expect(page.getByRole('heading', { name: 'Mục đích' })).toBeVisible()

  // Phase R3: bản nháp Khám phá gồm cả catalog trừ spec cần train (thay preset "Toàn bộ catalog").
  await wizardToAttacks(page, {
    slice: /3 ảnh/,
    beforeNext: async () => {
      await expect(page.getByText('Tự chọn class mapping duy nhất')).toBeVisible()
    },
  })
  // Catalog active đổi theo dữ liệu E2E (phase_r3/catalog kích hoạt thêm spec): đếm từ API.
  const catalog = await getJson<{ requires_training: boolean | null }[]>(page, '/attack-specs')
  const untrained = catalog.filter((spec) => !spec.requires_training).length
  expect(untrained).toBeGreaterThanOrEqual(9)
  const rows = page.getByTestId('attack-row')
  await expect(rows).toHaveCount(untrained)
  for (const kind of ['Tấn công', 'Biến đổi điều kiện', 'Che khuất']) {
    await expect(rows.getByText(kind, { exact: true }).first()).toBeVisible()
  }
  await page.getByText('Tùy chỉnh nâng cao: mọi attack').click()
  await expect(page.getByRole('switch', { name: 'Dừng sớm khi model đã sụp' })).toBeChecked()

  // Thêm adv_patch: chưa chọn slice huấn luyện thì chưa thêm được.
  await page.getByRole('button', { name: 'adv_patch', exact: true }).click()
  await expect(attackRow(page, 'adv_patch')).toHaveCount(0)
  const training = page.getByLabel('Slice huấn luyện', { exact: true })
  const options = training.locator('option:not([disabled])')
  await expect(options).toHaveCount(1) // chỉ slice 2 ảnh (không giao)
  await expect(options).toContainText('2 ảnh')
  await training.selectOption({ index: 1 })
  await expect(rows).toHaveCount(untrained + 1)
  const patch = attackRow(page, 'adv_patch')
  await expect(patch.locator('[data-level="0.1"]')).toBeVisible()
  await expect(patch.locator('[data-level="0.25"]')).toBeVisible()
  await setLevels(patch, [0.1, 0.25])
  await expect(visibleButton(page, 'Tạo experiment')).toBeEnabled()

  // Ước lượng có thời gian train patch.
  const estimate = page.locator('table', { has: page.getByText('Ước lượng từng run') })
  const patchRun = estimate.locator('tbody tr', {
    has: page.getByText('adv_patch', { exact: true }),
  })
  await expect(patchRun.first().locator('td').last()).not.toHaveText('—')
  await expectNoHorizontalScroll(page)
})
