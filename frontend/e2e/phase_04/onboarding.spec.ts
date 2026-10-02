// validation.md Phase 4, Frontend E2E: yêu cầu truy cập → chờ duyệt → duyệt / từ chối.
import { expect, test } from '@playwright/test'

import {
  ADMIN,
  loginUi,
  PASSWORD,
  requestAccessApi,
  uniqueEmail,
  visibleList,
  visibleNav,
} from './helpers'

test('người dùng mới yêu cầu truy cập, đăng nhập thấy màn hình "đang chờ duyệt"', async ({
  page,
}, info) => {
  const email = uniqueEmail(info, 'moi')
  await page.goto('/')
  await page.getByRole('link', { name: 'Yêu cầu truy cập' }).click()
  await page.getByLabel('Họ tên').fill('Người Mới')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Lý do cần truy cập').fill('Kiểm thử model')
  await page.getByLabel('Mật khẩu', { exact: true }).fill(PASSWORD)
  await page.getByLabel('Nhập lại mật khẩu').fill(PASSWORD)
  await page.getByRole('button', { name: 'Gửi yêu cầu' }).click()
  await expect(page).toHaveURL(/\/request-access\/sent$/)
  await loginUi(page, email)
  await expect(page).toHaveURL(/\/pending\?code=account_pending$/)
  await expect(page.getByRole('heading', { name: 'Tài khoản đang chờ duyệt' })).toBeVisible()
})

test('admin duyệt với role engineer; người dùng vào /home, điều hướng chỉ hiện mục được phép', async ({
  browser,
  request,
}, info) => {
  const email = uniqueEmail(info, 'duyet')
  await requestAccessApi(request, email, 'reviewer')
  const admin = await browser.newPage()
  await loginUi(admin, ADMIN.email, ADMIN.password)
  await visibleNav(admin, info).getByRole('link', { name: 'Người dùng' }).click()
  await expect(admin).toHaveURL(/\/admin\/users$/)
  const name = `Người ${email.split('@')[0]}`
  await visibleList(admin, info)
    .getByRole('button', { name: `Duyệt: ${name}` })
    .click()
  const dialog = admin.getByRole('dialog')
  await dialog.getByLabel('Kỹ sư an toàn (reviewer)').uncheck()
  await dialog.getByLabel('Kỹ sư ML/perception').check()
  await dialog.getByRole('button', { name: 'Duyệt' }).click()
  await expect(dialog).toBeHidden()

  const user = await browser.newPage()
  await loginUi(user, email)
  await expect(user).toHaveURL(/\/home$/)
  const nav = visibleNav(user, info)
  await expect(nav).toBeVisible()
  // Phase 5 Group 6: engineer có thêm "Experiment" và "Tạo experiment" (plan.md Phase 5, task 37).
  // Phase 8 Group 5: thêm "Protocol" (protocol.read); trên điện thoại 5 mục nên thanh tab còn
  // 3 mục đầu, "Protocol" và "Tài khoản" nằm trong "Thêm" (người dùng cho phép sửa, 2026-10-02).
  await expect(nav.getByRole('link', { name: 'Trang chủ' })).toBeVisible()
  await expect(nav.getByRole('link', { name: 'Experiment', exact: true })).toBeVisible()
  await expect(nav.getByRole('link', { name: 'Tạo experiment' })).toBeVisible()
  await expect(nav.getByRole('link', { name: 'Người dùng' })).toHaveCount(0)
  await expect(nav.getByRole('link', { name: 'Duyệt' })).toHaveCount(0)
  if (info.project.name === 'phone') {
    await expect(nav.getByRole('link')).toHaveCount(3)
    await nav.getByRole('button', { name: 'Thêm' }).click()
    const more = user.getByRole('dialog')
    await expect(more.getByRole('link')).toHaveCount(2)
    await expect(more.getByRole('link', { name: 'Protocol' })).toBeVisible()
    await expect(more.getByRole('link', { name: 'Tài khoản' })).toBeVisible()
  } else {
    await expect(nav.getByRole('link')).toHaveCount(5)
    await expect(nav.getByRole('link', { name: 'Protocol' })).toBeVisible()
    await expect(nav.getByRole('link', { name: 'Tài khoản' })).toBeVisible()
  }
})

test('admin từ chối kèm lý do; người đó đăng nhập thấy màn hình "bị từ chối"', async ({
  browser,
  request,
}, info) => {
  const email = uniqueEmail(info, 'tuchoi')
  await requestAccessApi(request, email)
  const admin = await browser.newPage()
  await loginUi(admin, ADMIN.email, ADMIN.password)
  await admin.goto('/admin/users')
  const name = `Người ${email.split('@')[0]}`
  await visibleList(admin, info)
    .getByRole('button', { name: `Từ chối: ${name}` })
    .click()
  const dialog = admin.getByRole('dialog')
  await expect(dialog.getByRole('button', { name: 'Từ chối' })).toBeDisabled()
  await dialog.getByLabel('Lý do từ chối (bắt buộc)').fill('Không thuộc nhóm dự án')
  await dialog.getByRole('button', { name: 'Từ chối' }).click()
  await expect(dialog).toBeHidden()

  const user = await browser.newPage()
  await loginUi(user, email)
  await expect(user).toHaveURL(/\/pending\?code=account_rejected$/)
  await expect(user.getByRole('heading', { name: 'Yêu cầu truy cập bị từ chối' })).toBeVisible()
})
