// validation.md Phase 5, Frontend E2E: giữ nháp khi tải lại, level sai bị chặn, nhân bản, quyền.
import { expect, test } from '@playwright/test'

import { activeUser, expectNoHorizontalScroll, loginUi, visibleNav } from '../phase_04/helpers'
import { addLevel, attackCard, createExperiment, visibleButton } from './helpers'

test('tải lại trang giữa wizard: dữ liệu đã nhập vẫn còn', async ({ page, request }, info) => {
  const email = await activeUser(request, info, ['engineer'])
  await loginUi(page, email)
  await page.goto('/experiments/new')
  await page.getByRole('radio', { name: /dev-open/ }).click()
  await visibleButton(page, /^Tiếp/).click()
  await page.getByRole('radio', { name: /yolov8n-coco/ }).click()
  await page.reload()
  await expect(page.getByRole('radio', { name: /yolov8n-coco/ })).toHaveAttribute(
    'aria-checked',
    'true',
  )
  await expect(page.getByRole('heading', { name: 'Model' })).toBeVisible()
})

test('nhập level ngoài dải: lỗi tại bước 4, không sang bước tiếp', async ({
  page,
  request,
}, info) => {
  const email = await activeUser(request, info, ['engineer'])
  await loginUi(page, email)
  await page.goto('/experiments/new')
  await page.getByRole('radio', { name: /dev-open/ }).click()
  await visibleButton(page, /^Tiếp/).click()
  await page.getByRole('radio', { name: /yolov8n-coco/ }).click()
  await visibleButton(page, /^Tiếp/).click()
  await page.getByRole('radiogroup', { name: 'Dataset version' }).getByRole('radio').first().click()
  await page
    .getByRole('radiogroup', { name: 'Slice' })
    .getByRole('radio', { name: /5 ảnh/ })
    .click()
  await visibleButton(page, /^Tiếp/).click()
  await page.getByLabel('fgsm v1', { exact: true }).check()
  await addLevel(attackCard(page, 'fgsm v1'), '99')
  await expect(page.getByText('Level 99 ngoài dải')).toBeVisible()
  await expect(visibleButton(page, /^Tiếp/)).toBeDisabled()
  await expect(page.getByRole('heading', { name: 'Attack' })).toBeVisible()
  await expectNoHorizontalScroll(page)
})

test('nhân bản: wizard mở tại bước 6 với dữ liệu điền sẵn', async ({ page, request }, info) => {
  const email = await activeUser(request, info, ['engineer'])
  await loginUi(page, email)
  const id = await createExperiment(page, [['fgsm', [2, 8]]])
  await page.goto(`/experiments/${id}`)
  await page.getByRole('link', { name: 'Nhân bản' }).click()
  await expect(page).toHaveURL(new RegExp(`/experiments/new\\?clone=${id}$`))
  await expect(page.getByRole('heading', { name: 'Xác nhận' })).toBeVisible()
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
