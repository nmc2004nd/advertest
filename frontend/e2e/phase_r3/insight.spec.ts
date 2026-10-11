// validation.md Phase R3, Group 5 — Kết quả mở đầu bằng insight (M3, M4) và nâng lên chính thức:
// - câu kết luận, điểm yếu, ma trận 4 dải có chú thích thang màu; ô không có level ghi "Chưa chạy";
// - bấm điểm yếu mở tab Failure case đã lọc theo attack và level;
// - mỗi biểu đồ có nút "Cách đọc"; thuật ngữ mở tooltip bằng bàn phím, đóng bằng Esc;
// - experiment chưa có kết quả: trạng thái trống, không có ma trận;
// - "Nâng lên chính thức" → chọn protocol → wizard bước 3 → experiment mới có link tới nguồn.
import { expect, test } from '@playwright/test'

import { expectNoHorizontalScroll } from '../phase_04/helpers'
import { cancelExperiment, visibleButton } from '../phase_05/helpers'
import { createProtocolApi, userPage, waitStatus } from '../phase_08/helpers'
import { chooseOption, DEV_OPEN, experimentApi, getJson, WORKER_TIMEOUT } from './helpers'

test.setTimeout(WORKER_TIMEOUT + 120_000)

test('tab Kết quả mở đầu bằng kết luận, điểm yếu và ma trận', async ({ browser }, info) => {
  const { page } = await userPage(browser, info, ['engineer'])
  // FGSM max 32: level 4 và 8 thuộc dải 1, 16 thuộc dải 2; dải 3 và 4 không có level.
  const id = await experimentApi(page, [4, 8, 16])
  await waitStatus(page, id, 'completed')
  await page.goto(`/experiments/${id}?tab=results`)

  await expect(page.getByTestId('insight-conclusion')).not.toBeEmpty()
  const matrix = page.getByTestId('robustness-matrix')
  await expect(matrix.getByTestId('matrix-cell')).toHaveCount(4)
  await expect(matrix.getByTestId('matrix-cell').nth(3)).toContainText('Chưa chạy')
  await expect(page.getByTestId('matrix-legend')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Cách đọc' }).first()).toBeVisible()
  await expectNoHorizontalScroll(page)

  const term = page.locator('[data-term]').first()
  await term.focus()
  const tooltip = page.getByRole('tooltip')
  await expect(tooltip).toBeVisible()
  await expect(term).toHaveAttribute('aria-describedby', (await tooltip.getAttribute('id')) ?? '')
  await page.keyboard.press('Escape')
  await expect(tooltip).toBeHidden()

  const weakness = page.getByTestId('weakness').first()
  await expect(weakness).toBeVisible()
  const level = await weakness.getAttribute('data-level')
  await weakness.click()
  await expect(page.getByRole('tab', { name: 'Failure case' })).toHaveAttribute(
    'aria-selected',
    'true',
  )
  await expect(page).toHaveURL(
    new RegExp(`attack=fgsm.*level=${level}|level=${level}.*attack=fgsm`),
  )
})

test('chưa có kết quả: trạng thái trống, không có ma trận', async ({ browser }, info) => {
  const { page } = await userPage(browser, info, ['engineer'])
  // Máy không có worker: experiment nằm chờ (trên local-dev, fgsm [2] trúng cache và xong ngay).
  const id = await experimentApi(page, [2], DEV_OPEN, 'e2e-offline')
  await page.goto(`/experiments/${id}?tab=results`)
  await expect(page.getByTestId('empty-state')).toBeVisible()
  await expect(page.getByTestId('robustness-matrix')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Nâng lên chính thức' })).toHaveCount(0)
  await cancelExperiment(page, id)
})

test('nâng lên chính thức đi qua wizard bước 3', async ({ browser }, info) => {
  const reviewer = await userPage(browser, info, ['reviewer'])
  const protocol = await createProtocolApi(reviewer.page, [3, 4])
  const protocolName = (await getJson<{ name: string }>(reviewer.page, `/protocols/${protocol.id}`))
    .name
  const { page } = await userPage(browser, info, ['engineer'])
  const source = await experimentApi(page, [2])
  await waitStatus(page, source, 'completed')
  const sourceName = (await getJson<{ name: string }>(page, `/experiments/${source}`)).name

  await page.goto(`/experiments/${source}?tab=results`)
  await visibleButton(page, 'Nâng lên chính thức').click()
  const dialog = page.getByRole('dialog')
  await chooseOption(page, 'Protocol', protocolName)
  await dialog.getByRole('button', { name: 'Tiếp tục' }).click()
  await expect(page).toHaveURL(/\/experiments\/new/)
  await expect(page.getByTestId('wizard-step').nth(2)).toHaveAttribute('aria-current', 'step')
  await visibleButton(page, 'Tạo experiment').click()
  await expect(page).toHaveURL(/\/experiments\/[0-9a-f-]{36}$/)
  const created = page.url().split('/').pop() ?? ''
  expect(created).not.toBe(source)
  await expect(page.getByTestId('experiment-mode')).toHaveText(/Chính thức/)
  await expect(page.getByRole('link', { name: new RegExp(`Nâng từ.*${sourceName}`) })).toBeVisible()
  await cancelExperiment(page, created)
})
