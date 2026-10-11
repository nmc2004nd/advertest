// validation.md Phase R3, Group 4 — Trang experiment là trung tâm (M1) và ý nghĩa quyết định (M5):
// - đúng 5 tab: Tổng quan, Kết quả, Failure case, Review, Report;
// - thanh vòng đời: Khám phá chỉ có Tạo → Chạy → Phân tích; Chính thức có đủ 6 bước;
// - nhãn mode; `?tab=cost` và `?tab=repro` mở Tổng quan, đúng section;
// - tab Review chưa gửi duyệt hiện trạng thái trống;
// - hộp xác nhận gửi duyệt có bảng ý nghĩa quyết định;
// - không cuộn ngang.
import { expect, test } from '@playwright/test'

import { expectNoHorizontalScroll } from '../phase_04/helpers'
import { createProtocolApi, userPage, waitStatus } from '../phase_08/helpers'
import { experimentApi, lifecycle, PROTOCOL_LEVELS, SERVER_WAIT, WORKER_TIMEOUT } from './helpers'

const TABS = ['Tổng quan', 'Kết quả', 'Failure case', 'Review', 'Report']

test.setTimeout(WORKER_TIMEOUT + 120_000)

test('experiment Khám phá: 5 tab, vòng đời 3 bước, section chuyển từ tab cũ', async ({
  browser,
}, info) => {
  const { page } = await userPage(browser, info, ['engineer'])
  const id = await experimentApi(page, [4])
  await waitStatus(page, id, 'completed')

  await page.goto(`/experiments/${id}`)
  await expect(page.getByRole('tab')).toHaveText(TABS, { timeout: SERVER_WAIT })
  await expect(page.getByTestId('experiment-mode')).toHaveText(/Khám phá/)
  expect(await lifecycle(page)).toEqual({ create: 'done', run: 'done', analyze: 'current' })
  await expectNoHorizontalScroll(page)

  for (const [tab, heading] of [
    ['cost', 'Chi phí'],
    ['repro', 'Tái lập'],
  ]) {
    await page.goto(`/experiments/${id}?tab=${tab}`)
    await expect(page.getByRole('tab', { name: 'Tổng quan' })).toHaveAttribute(
      'aria-selected',
      'true',
    )
    await expect(page.getByRole('heading', { name: heading })).toBeInViewport()
  }

  await page.getByRole('tab', { name: 'Review' }).click()
  await expect(page.getByTestId('empty-state')).toBeVisible()
  await page.getByRole('tab', { name: 'Report' }).click()
  await expect(page.getByTestId('empty-state')).toBeVisible()
})

test('experiment Chính thức: vòng đời 6 bước, hộp gửi duyệt có ý nghĩa quyết định', async ({
  browser,
}, info) => {
  const reviewer = await userPage(browser, info, ['reviewer'])
  const protocol = await createProtocolApi(reviewer.page, PROTOCOL_LEVELS)
  const { page } = await userPage(browser, info, ['engineer'])
  const id = await experimentApi(page, PROTOCOL_LEVELS, protocol.id)
  await waitStatus(page, id, 'completed')

  await page.goto(`/experiments/${id}`)
  await expect(page.getByTestId('experiment-mode')).toHaveText(/Chính thức/)
  expect(await lifecycle(page)).toEqual({
    create: 'done',
    run: 'done',
    analyze: 'current',
    submit: 'todo',
    review: 'todo',
    report: 'todo',
  })

  await page.getByRole('button', { name: 'Gửi duyệt' }).filter({ visible: true }).first().click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByTestId('decision-meaning')).toBeVisible()
  await expect(dialog.getByTestId('decision-meaning')).toContainText('khóa')
  await expectNoHorizontalScroll(page)
})
