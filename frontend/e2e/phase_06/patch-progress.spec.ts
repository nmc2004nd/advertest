// validation.md Phase 6, Frontend E2E: run patch hiển thị "Đang train patch (x/4)" (seed adv_patch
// max_iter = 4 của scripts/e2e.sh) rồi chạy xong. Mỗi viewport một area_ratio riêng để patch phải
// train (3 viewport chạy nối tiếp trên cùng DB, khóa đã có thì không train lại).
import { expect, test } from '@playwright/test'

import { activeUser, loginUi } from '../phase_04/helpers'
import { createPhase06Experiment, RUN_TIMEOUT, waitCompleted } from './helpers'

const AREA_RATIO: Record<string, number> = { phone: 0.06, tablet: 0.07, desktop: 0.08 }

test('run patch: giai đoạn train hiển thị trên bảng run', async ({ page, request }, info) => {
  test.setTimeout(RUN_TIMEOUT + 60_000)
  const email = await activeUser(request, info, ['engineer'])
  await loginUi(page, email)
  const id = await createPhase06Experiment(page, [['adv_patch', [AREA_RATIO[info.project.name]]]])
  await page.goto(`/experiments/${id}`)
  await expect(page.getByText(/Đang train patch \(\d\/4\)/)).toBeVisible({ timeout: RUN_TIMEOUT })
  await waitCompleted(page, id)
  await expect(
    page.locator('[data-kind="experiment"][data-status="completed"]').first(),
  ).toBeVisible()
})
