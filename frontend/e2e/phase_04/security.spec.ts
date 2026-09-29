// validation.md Phase 4, Manual Checks làm được bằng máy: hai trình duyệt và cookie.
import { expect, test } from '@playwright/test'

import { activeUser, adminApi, loginUi } from './helpers'

test('hai trình duyệt: admin vô hiệu hóa, người kia bị đăng xuất ở thao tác kế tiếp', async ({
  browser,
  request,
}, info) => {
  const email = await activeUser(request, info, ['engineer'])
  const other = await browser.newContext()
  const page = await other.newPage()
  await loginUi(page, email)
  await expect(page).toHaveURL(/\/home$/)
  await (await adminApi(request)).disable(email)
  await page.reload()
  await expect(page).toHaveURL(/\/login\?next=%2Fhome$/)
  await other.close()
})

test('cookie đúng cờ; không có dữ liệu nhạy cảm trong cookie hay localStorage', async ({
  page,
  context,
  request,
}, info) => {
  const email = await activeUser(request, info, ['engineer'])
  await loginUi(page, email)
  await expect(page).toHaveURL(/\/home$/)
  const cookies = await context.cookies()
  const session = cookies.find((c) => c.name === 'advertest_session')
  const csrf = cookies.find((c) => c.name === 'csrf_token')
  expect(session).toMatchObject({ httpOnly: true, sameSite: 'Lax', path: '/' })
  expect(csrf).toMatchObject({ httpOnly: false, sameSite: 'Lax' })
  for (const cookie of cookies) {
    expect(cookie.value).not.toContain(email)
    expect(cookie.value).not.toContain('mat-khau')
  }
  const storage = await page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }))
  expect(storage).toBe('{}')
})
