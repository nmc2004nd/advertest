// validation.md Phase 4, Frontend E2E: bố cục theo viewport (390 / 820 / 1440) và /home của admin.
import { expect, test } from '@playwright/test'

import {
  activeUser,
  adminApi,
  ADMIN,
  expectNoHorizontalScroll,
  loginUi,
  visibleList,
} from './helpers'

test('bố cục điều hướng và danh sách đúng theo viewport; không trang nào cuộn ngang', async ({
  page,
  request,
}, info) => {
  const target = await activeUser(request, info, ['engineer'])
  await loginUi(page, ADMIN.email, ADMIN.password)
  await expect(page).toHaveURL(/\/home$/)
  const aside = page.locator('aside[aria-label="Điều hướng chính"]')
  const tabs = page.locator('nav[aria-label="Điều hướng chính"]')

  if (info.project.name === 'phone') {
    await expect(tabs).toBeVisible()
    await expect(aside).toBeHidden()
  } else if (info.project.name === 'tablet') {
    // Cột icon: sidebar hẹp, nhãn ẩn (chỉ còn icon, tên nằm ở aria-label).
    await expect(aside).toBeVisible()
    await expect(tabs).toBeHidden()
    expect((await aside.boundingBox())?.width).toBeLessThanOrEqual(80)
    await expect(aside.getByText('Người dùng', { exact: true })).toBeHidden()
  } else {
    await expect(aside).toBeVisible()
    await expect(tabs).toBeHidden()
    expect((await aside.boundingBox())?.width).toBeGreaterThanOrEqual(200)
    await expect(aside.getByText('Người dùng', { exact: true })).toBeVisible()
  }

  for (const path of ['/home', '/account', '/admin/users', '/admin/audit']) {
    await page.goto(path)
    await expect(page.locator('h1')).toBeVisible()
    await expectNoHorizontalScroll(page)
  }
  for (const path of ['/admin/users', '/admin/audit']) {
    await page.goto(path)
    const table = page.locator('table')
    if (info.project.name === 'desktop') await expect(table).toBeVisible()
    else await expect(table).toBeHidden()
  }

  // Hộp xác nhận: bottom sheet sát đáy trên điện thoại, hộp giữa màn hình ở tablet/desktop.
  await page.goto('/admin/users')
  await page.getByRole('tab', { name: 'Tất cả' }).click()
  const name = `Người ${target.split('@')[0]}`
  await visibleList(page, info)
    .getByRole('button', { name: `Vô hiệu hóa: ${name}` })
    .click()
  const box = await page.getByRole('dialog').boundingBox()
  const viewport = page.viewportSize()
  expect(box && viewport).toBeTruthy()
  if (box && viewport) {
    const bottomGap = viewport.height - (box.y + box.height)
    if (info.project.name === 'phone') {
      expect(bottomGap).toBeLessThanOrEqual(1)
      expect(box.width).toBeGreaterThanOrEqual(viewport.width - 1)
    } else {
      expect(bottomGap).toBeGreaterThan(20)
    }
  }
  await page.getByRole('button', { name: 'Hủy' }).click()

  for (const path of ['/', '/login', '/request-access']) {
    await page.goto(path)
    await expectNoHorizontalScroll(page)
  }
})

test('admin thấy khối "tài khoản chờ duyệt" trên /home với đúng số lượng', async ({
  page,
  request,
}) => {
  const expected = await (await adminApi(request)).pendingCount()
  await loginUi(page, ADMIN.email, ADMIN.password)
  await expect(page).toHaveURL(/\/home$/)
  const count = page.getByTestId('so-cho-duyet')
  await expect(count).toHaveText(expected >= 100 ? /^\d+\+?$/ : String(expected))
  await expect(page.getByText('tài khoản chờ duyệt')).toBeVisible()
})
