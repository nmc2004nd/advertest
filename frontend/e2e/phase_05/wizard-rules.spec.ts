// validation.md Phase 5, Frontend E2E: giữ nháp khi tải lại, level sai bị chặn, nhân bản, quyền.
// Phase R3 (plan.md task 23a): wizard 3 bước.
import { expect, test } from '@playwright/test'

import { activeUser, expectNoHorizontalScroll, loginUi, visibleNav } from '../phase_04/helpers'
import {
  attackRow,
  chooseOption,
  nextStep,
  selectedOption,
  setLevels,
  wizardToAttacks,
} from '../phase_r3/helpers'
import { createExperiment, visibleButton } from './helpers'

test('tải lại trang giữa wizard: dữ liệu đã nhập vẫn còn', async ({ page, request }, info) => {
  const email = await activeUser(request, info, ['engineer'])
  await loginUi(page, email)
  await page.goto('/experiments/new')
  await page
    .getByRole('radiogroup', { name: 'Mode' })
    .getByRole('radio', { name: /Khám phá/ })
    .check()
  await nextStep(page)
  await chooseOption(page, 'Model', 'yolov8n-coco')
  await page.reload()
  await expect(selectedOption(page, 'Model')).toHaveText(/yolov8n-coco/)
  await expect(page.getByRole('heading', { name: 'Model và dữ liệu' })).toBeVisible()
})

// Phase R3 (M2): không còn ô gõ level; level chọn bằng chip, chỉ có giá trị trong dải của spec.
// Thay cho "nhập level ngoài dải": attack không còn level nào thì không tạo được experiment.
test('level chỉ chọn trong dải; attack không có level: không tạo được, ở lại bước 3', async ({
  page,
  request,
}, info) => {
  const email = await activeUser(request, info, ['engineer'])
  await loginUi(page, email)
  await wizardToAttacks(page)
  const fgsm = attackRow(page, 'fgsm')
  for (const chip of await fgsm.locator('[data-level]').all()) {
    const level = Number(await chip.getAttribute('data-level'))
    expect(level).toBeGreaterThanOrEqual(0)
    expect(level).toBeLessThanOrEqual(32)
  }
  await setLevels(fgsm, [])
  await expect(visibleButton(page, 'Tạo experiment')).toBeDisabled()
  await expect(page.getByRole('heading', { name: 'Attack và xác nhận' })).toBeVisible()
  await expectNoHorizontalScroll(page)
})

test('nhân bản: wizard mở tại bước 3 với dữ liệu điền sẵn', async ({ page, request }, info) => {
  const email = await activeUser(request, info, ['engineer'])
  await loginUi(page, email)
  const id = await createExperiment(page, [['fgsm', [2, 8]]])
  await page.goto(`/experiments/${id}`)
  await page.getByRole('link', { name: 'Nhân bản' }).click()
  await expect(page).toHaveURL(new RegExp(`/experiments/new\\?clone=${id}$`))
  await expect(page.getByRole('heading', { name: 'Attack và xác nhận' })).toBeVisible()
  await expect(page.getByText('fgsm: 2, 8').first()).toBeAttached()
})

test('reviewer không thấy "Tạo experiment"; vào thẳng /experiments/new bị chặn', async ({
  page,
  request,
}, info) => {
  const email = await activeUser(request, info, ['reviewer'])
  await loginUi(page, email)
  const nav = visibleNav(page, info)
  await expect(nav.getByRole('link', { name: 'Experiment', exact: true })).toBeVisible()
  await expect(nav.getByRole('link', { name: 'Tạo experiment' })).toHaveCount(0)
  await page.goto('/experiments/new')
  await expect(page).toHaveURL(/\/forbidden$/)
})
