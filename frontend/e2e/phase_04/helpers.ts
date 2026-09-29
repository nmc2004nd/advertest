// Tiện ích cho kịch bản E2E Phase 4 (backend thật qua proxy /api, xem scripts/e2e.sh).
import { expect, type APIRequestContext, type Page, type TestInfo } from '@playwright/test'

export const ADMIN = {
  email: process.env.ADVERTEST_ADMIN_EMAIL ?? 'admin@e2e.test',
  password: process.env.ADVERTEST_ADMIN_PASSWORD ?? 'e2e-admin-password',
}
export const PASSWORD = 'mat-khau-du-dai-1'

export function uniqueEmail(info: TestInfo, prefix: string): string {
  return `${prefix}-${info.project.name}-${Date.now()}-${Math.floor(Math.random() * 1e6)}@e2e.test`
}

export async function requestAccessApi(
  request: APIRequestContext,
  email: string,
  role: 'engineer' | 'reviewer' | 'admin' = 'engineer',
): Promise<void> {
  const response = await request.post('/api/auth/request-access', {
    data: {
      full_name: `Người ${email.split('@')[0]}`,
      email,
      organization: 'E2E',
      requested_role: role,
      reason: 'Kiểm thử E2E Phase 4',
      password: PASSWORD,
    },
  })
  expect(response.status()).toBe(202)
}

/** Admin qua API (thiết lập dữ liệu); giao diện admin được kiểm tra ở kịch bản riêng. */
async function csrfHeader(request: APIRequestContext): Promise<Record<string, string>> {
  const csrf = (await request.storageState()).cookies.find((c) => c.name === 'csrf_token')?.value
  return { 'X-CSRF-Token': csrf ?? '' }
}

export async function adminApi(request: APIRequestContext) {
  // Context đã có cookie phiên thì request thay đổi dữ liệu (kể cả đăng nhập lại) cần CSRF token.
  const login = await request.post('/api/auth/login', {
    data: ADMIN,
    headers: await csrfHeader(request),
  })
  expect(login.status()).toBe(200)
  const headers = await csrfHeader(request)
  async function userId(email: string): Promise<string> {
    const list = await (await request.get('/api/admin/users?limit=100')).json()
    const user = list.items.find((u: { email: string }) => u.email === email)
    expect(user, email).toBeTruthy()
    return user.id
  }
  return {
    async approve(email: string, roles: string[]) {
      const id = await userId(email)
      const r = await request.post(`/api/admin/users/${id}/approve`, { data: { roles }, headers })
      expect(r.status()).toBe(200)
    },
    async disable(email: string) {
      const id = await userId(email)
      const r = await request.post(`/api/admin/users/${id}/disable`, { headers })
      expect(r.status()).toBe(200)
    },
    async pendingCount(): Promise<number> {
      const page = await (await request.get('/api/admin/users?status=pending&limit=100')).json()
      return page.items.length
    },
  }
}

/** Người dùng đã được duyệt với `roles` (tạo và duyệt qua API). */
export async function activeUser(
  request: APIRequestContext,
  info: TestInfo,
  roles: string[],
): Promise<string> {
  const email = uniqueEmail(info, roles.join('-'))
  await requestAccessApi(request, email, roles[0] as 'engineer')
  await (await adminApi(request)).approve(email, roles)
  return email
}

export async function loginUi(page: Page, email: string, password = PASSWORD): Promise<void> {
  await page.goto('/login')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Mật khẩu').fill(password)
  await page.getByRole('button', { name: 'Đăng nhập' }).click()
  // Chờ đăng nhập xong (rời /login: tới trang đích hoặc /pending) trước thao tác kế tiếp.
  await page.waitForURL((url) => url.pathname !== '/login')
}

export async function expectNoHorizontalScroll(page: Page): Promise<void> {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)
  expect(overflow, page.url()).toBeLessThanOrEqual(0)
}

/** Khu vực điều hướng đang hiển thị theo viewport: thanh tab (điện thoại) hoặc sidebar/cột icon. */
export function visibleNav(page: Page, info: TestInfo) {
  return info.project.name === 'phone'
    ? page.locator('nav[aria-label="Điều hướng chính"]')
    : page.locator('aside[aria-label="Điều hướng chính"]')
}

/** Danh sách đang hiển thị: bảng từ 1280px (desktop), thẻ dưới 1280px. */
export function visibleList(page: Page, info: TestInfo) {
  return info.project.name === 'desktop' ? page.locator('table') : page.locator('ul.xl\\:hidden')
}
