// validation.md Phase 4, Frontend E2E: chặn trang theo quyền, hết phiên, bàn phím.
import { expect, test } from '@playwright/test'

import { activeUser, loginUi, PASSWORD, uniqueEmail } from './helpers'

test('engineer vào thẳng /admin/users bị chuyển tới /forbidden', async ({
  page,
  request,
}, info) => {
  const email = await activeUser(request, info, ['engineer'])
  await loginUi(page, email)
  await expect(page).toHaveURL(/\/home$/)
  await page.goto('/admin/users')
  await expect(page).toHaveURL(/\/forbidden$/)
  await expect(page.getByRole('heading', { name: 'Không có quyền truy cập' })).toBeVisible()
})

test('hết phiên: thao tác tiếp theo đưa về /login, đăng nhập xong quay lại đúng trang', async ({
  page,
  context,
  request,
}, info) => {
  const email = await activeUser(request, info, ['engineer'])
  await loginUi(page, email)
  await page.goto('/account')
  await expect(page.getByRole('heading', { name: 'Tài khoản' })).toBeVisible()
  await context.clearCookies()
  await page.getByLabel('Mật khẩu hiện tại').fill(PASSWORD)
  await page.getByLabel('Mật khẩu mới', { exact: true }).fill('mat-khau-moi-dai-2')
  await page.getByLabel('Nhập lại mật khẩu mới').fill('mat-khau-moi-dai-2')
  await page.getByRole('button', { name: 'Đổi mật khẩu' }).click()
  await expect(page).toHaveURL(/\/login\?next=%2Faccount$/)
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Mật khẩu').fill(PASSWORD)
  await page.getByRole('button', { name: 'Đăng nhập' }).click()
  await expect(page).toHaveURL(/\/account$/)
})

async function tabTo(page: import('@playwright/test').Page, label: string): Promise<void> {
  for (let i = 0; i < 15; i += 1) {
    await page.keyboard.press('Tab')
    const focused = await page.evaluate(() => {
      const el = document.activeElement
      return el && el.id ? document.querySelector(`label[for="${el.id}"]`)?.textContent : null
    })
    if (focused === label) return
  }
  throw new Error(`Không tới được ô "${label}" bằng Tab`)
}

test('điều hướng toàn bộ form đăng nhập bằng bàn phím', async ({ page, request }, info) => {
  const email = await activeUser(request, info, ['engineer'])
  await page.goto('/login')
  await tabTo(page, 'Email')
  await page.keyboard.type(email)
  await page.keyboard.press('Tab')
  await page.keyboard.type(PASSWORD)
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/\/home$/)
})

test('điều hướng toàn bộ form yêu cầu truy cập bằng bàn phím', async ({ page }, info) => {
  await page.goto('/request-access')
  await tabTo(page, 'Họ tên')
  await page.keyboard.type('Người Bàn Phím')
  await page.keyboard.press('Tab')
  await page.keyboard.type(uniqueEmail(info, 'banphim'))
  await page.keyboard.press('Tab')
  await page.keyboard.type('E2E')
  await page.keyboard.press('Tab')
  await page.keyboard.press('ArrowDown') // Vai trò đề nghị: engineer → reviewer
  await page.keyboard.press('Tab')
  await page.keyboard.type('Dùng bàn phím')
  await page.keyboard.press('Tab')
  await page.keyboard.type(PASSWORD)
  await page.keyboard.press('Tab')
  await page.keyboard.type(PASSWORD)
  await page.keyboard.press('Tab')
  await expect(page.getByRole('button', { name: 'Gửi yêu cầu' })).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/\/request-access\/sent$/)
})
