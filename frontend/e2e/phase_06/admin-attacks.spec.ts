// validation.md Phase 6, Frontend E2E: admin mở /admin/attacks thấy đủ 10 spec (thẻ dưới 1280px,
// bảng từ 1280px, không cuộn ngang); engineer bị chuyển tới /forbidden.
import { expect, test } from '@playwright/test'

import {
  activeUser,
  ADMIN,
  expectNoHorizontalScroll,
  loginUi,
  visibleList,
} from '../phase_04/helpers'

const NAMES = [
  'fgsm',
  'pgd_linf',
  'pgd_l2',
  'fog',
  'snow',
  'frost',
  'motion_blur',
  'contrast',
  'bbox_occlusion',
  'adv_patch',
]

test('admin thấy đủ catalog; engineer bị chặn', async ({ page, request }, info) => {
  await loginUi(page, ADMIN.email, ADMIN.password)
  await page.goto('/admin/attacks')
  await expect(page.getByRole('heading', { name: 'Attack catalog' })).toBeVisible()
  const list = visibleList(page, info)
  await expect(list).toBeVisible()
  for (const name of NAMES) {
    await expect(list.getByText(new RegExp(`^${name}( v\\d+)?$`)).first()).toBeVisible()
  }
  await expectNoHorizontalScroll(page)

  await page.context().clearCookies()
  const email = await activeUser(request, info, ['engineer'])
  await loginUi(page, email)
  await page.goto('/admin/attacks')
  await expect(page).toHaveURL(/\/forbidden$/)
})
