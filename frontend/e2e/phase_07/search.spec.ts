// validation.md Phase 7, Frontend E2E (backend, worker CPU thật, fixture 5 ảnh của scripts/e2e.sh):
// - wizard điền tol mặc định (hi − lo)/256 và cảnh báo tập con dưới 20 ảnh; công tắc tìm ngưỡng của
//   adv_patch bị khóa kèm giải thích;
// - engineer tạo experiment tìm ngưỡng PGD L∞, bước 6 hiển thị "tối đa"; khi chạy dòng tiến độ tìm
//   kiếm cập nhật; khi xong thẻ tóm tắt và biểu đồ quỹ đạo hiển thị;
// - 390px: chỉ thẻ tóm tắt, chạm thẻ mở quỹ đạo toàn màn hình, không cuộn ngang;
// - nháp wizard lưu theo định dạng trước Phase 7 mở được, attack là quét lưới, không mất trường nào.
// Câu kết luận theo từng trạng thái, nhãn "> 100%"/"≤ mức nhỏ nhất", thẻ failed/stopped_limit chỉ có
// trong mock: kiểm bằng Vitest (BreakpointCard.test.tsx, breakpoints.test.ts).
import { expect, type Page, test } from '@playwright/test'

import { activeUser, expectNoHorizontalScroll, loginUi } from '../phase_04/helpers'
import { attackCard, fixtureIds, visibleButton } from '../phase_05/helpers'

const RUN_TIMEOUT = 300_000
// Mỗi viewport một cận trên khác nhau: level thô khác nên worker phải chạy thật (không trúng cache
// của viewport trước), dòng tiến độ mới kịp hiện.
const HI: Record<string, string> = { phone: '16', tablet: '15', desktop: '14' }

async function toAttackStep(page: Page) {
  const next = () => visibleButton(page, /^Tiếp/).click()
  await page.goto('/experiments/new')
  await page.getByRole('radio', { name: /dev-open/ }).click()
  await next()
  await page.getByRole('radio', { name: /yolov8n-coco/ }).click()
  await next()
  await page.getByRole('radiogroup', { name: 'Dataset version' }).getByRole('radio').first().click()
  await page
    .getByRole('radiogroup', { name: 'Slice' })
    .getByRole('radio', { name: /5 ảnh/ })
    .click()
  await expect(page.getByText('Tự chọn mapping duy nhất')).toBeVisible()
  await next()
  await expect(page.getByRole('heading', { name: 'Tấn công', exact: true })).toBeVisible()
  return next
}

test('tìm ngưỡng PGD: wizard, chi phí tối đa, tiến độ, thẻ tóm tắt và quỹ đạo', async ({
  page,
  request,
}, info) => {
  test.setTimeout(RUN_TIMEOUT + 120_000)
  const email = await activeUser(request, info, ['engineer'])
  await loginUi(page, email)
  const next = await toAttackStep(page)

  // adv_patch: công tắc tìm ngưỡng bị khóa, có giải thích.
  await page.getByLabel('adv_patch v2', { exact: true }).check()
  const patch = attackCard(page, 'adv_patch v2')
  await expect(patch.getByRole('radio', { name: 'Tự tìm ngưỡng' })).toBeDisabled()
  await expect(patch.getByTestId('tim-nguong-khoa')).toContainText('train patch')
  await page.getByLabel('adv_patch v2', { exact: true }).uncheck()

  // PGD L∞: tự tìm ngưỡng. Dải mặc định 0–32, tol mặc định 32/256 = 0.125.
  await page.getByLabel('pgd_linf v1', { exact: true }).check()
  const pgd = attackCard(page, 'pgd_linf v1')
  await pgd.getByRole('radio', { name: 'Tự tìm ngưỡng' }).click()
  await expect(pgd.getByLabel(/^Từ/)).toHaveValue('0')
  await expect(pgd.getByLabel(/^Đến/)).toHaveValue('32')
  await expect(pgd.getByLabel(/^Độ chính xác/)).toHaveValue('0.125')
  // Dải nhỏ cho CPU; tol 2 như test backend. Tập con 3 ảnh (slice 5 ảnh): cảnh báo dưới 20.
  await pgd.getByLabel(/^Đến/).fill(HI[info.project.name])
  await pgd.getByLabel(/^Độ chính xác/).fill('2')
  await pgd.getByText('Nâng cao').click()
  await pgd.getByLabel(/^Kích thước tập con/).fill('3')
  await expect(pgd.getByTestId('tap-con-nho')).toBeVisible()
  await expectNoHorizontalScroll(page)
  await next()

  // Bước 5: thẻ máy chạy hiện ước lượng tối đa. DB của E2E mới: lần đầu máy chưa có số đo của PGD
  // (worker tự đo) nên chỉ có số điểm tối đa; các viewport sau có cả thời gian.
  await expect(page.getByRole('radio', { name: /local-dev/ })).toContainText(
    /Ước lượng: (tối đa ~.+|chưa ước lượng được tối đa) \(tối đa \d+ điểm\)/,
  )
  await next()

  // Bước 6: chi phí tối đa từng attack.
  await expect(page.getByTestId('chi-phi-tim-nguong')).toContainText(
    /pgd_linf: (Tối đa ~.+|Chưa đo được tốc độ trên máy này) \(tối đa \d+ điểm\)/,
  )
  await visibleButton(page, /^Chạy/).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog).toContainText(/tìm ngưỡng tối đa \d+ điểm/)
  await dialog.getByRole('button', { name: 'Chạy experiment' }).click()
  await expect(page).toHaveURL(/\/experiments\/[0-9a-f-]{36}$/)

  // Khi chạy: dòng tiến độ trong thẻ ở tab Kết quả, tăng dần không cần tải lại trang.
  await page.getByRole('tab', { name: 'Kết quả' }).click()
  const progress = page.getByTestId('tien-do-tim-nguong')
  await expect(progress).toContainText(/Điểm \d+ \/ tối đa \d+ · khoảng hiện tại/, {
    timeout: RUN_TIMEOUT,
  })
  const first = Number((await progress.textContent())?.match(/Điểm (\d+)/)?.[1])
  await expect
    .poll(
      async () => {
        if ((await progress.count()) === 0) return Number.POSITIVE_INFINITY // đã xong
        return Number((await progress.textContent())?.match(/Điểm (\d+)/)?.[1])
      },
      { timeout: RUN_TIMEOUT },
    )
    .toBeGreaterThan(first)

  // Khi xong: thẻ tóm tắt có câu kết luận.
  const conclusion = page.getByTestId('ket-luan-diem-gay')
  await expect(conclusion).toContainText(/Gãy tại eps ≈ .+\/255|Gãy ngay ở mức nhỏ nhất/, {
    timeout: RUN_TIMEOUT,
  })
  await expect(progress).toHaveCount(0)

  if (info.project.name === 'phone') {
    // Điện thoại: chỉ thẻ; chạm thẻ mở quỹ đạo toàn màn hình.
    await expect(page.getByTestId('diem-gay-chi-tiet')).toBeHidden()
    await page.getByRole('button', { name: 'Mở quỹ đạo của pgd_linf' }).click()
    const sheet = page.getByRole('dialog')
    await expect(sheet.locator('svg.recharts-surface').first()).toBeVisible()
    await expect(sheet.getByText('Quỹ đạo tìm ngưỡng của pgd_linf')).toBeAttached()
    const box = await sheet.boundingBox()
    expect(box?.width).toBe(390)
    expect(box?.height).toBe(844)
    await expectNoHorizontalScroll(page)
    await sheet.getByRole('button', { name: 'Đóng' }).click()
  } else {
    const detail = page.getByTestId('diem-gay-chi-tiet')
    await expect(detail).toBeVisible()
    await expect(detail.getByText('So sánh điểm gãy')).toBeVisible()
    await expect(detail.locator('svg.recharts-surface').first()).toBeVisible()
    await expect(detail.getByText('Quỹ đạo tìm ngưỡng của pgd_linf')).toBeAttached()
  }
  await expectNoHorizontalScroll(page)
})

test('nháp wizard lưu trước Phase 7 mở được: attack là quét lưới, không mất trường', async ({
  page,
  request,
}, info) => {
  const email = await activeUser(request, info, ['engineer'])
  await loginUi(page, email)
  const ids = await fixtureIds(page)
  const slices = (await (await page.request.get('/api/slices')).json()) as {
    id: string
    dataset_version_id: string
  }[]
  const datasetVersionId = slices.find((s) => s.id === ids.sliceId)?.dataset_version_id
  const fgsm = ids.spec('fgsm')
  // Định dạng nháp Phase 6 (khóa v2): attack không có mode/search.
  const draft = {
    step: 4,
    protocolId: '2edcdef5-0d3a-5d5f-98ac-b02637fa6718',
    modelId: ids.modelId,
    datasetVersionId,
    sliceId: ids.sliceId,
    mappingId: ids.mappingId,
    targetId: null,
    limitSeconds: null,
    attacks: [
      {
        attackSpecId: fgsm.id,
        specSha256: fgsm.spec_sha256,
        levels: [2, 8],
        requiresTraining: false,
        trainingSliceId: null,
      },
    ],
    earlyStop: false,
    earlyStopMixed: false,
    name: 'nháp cũ',
    clonedFrom: null,
    cloneWarnings: [],
  }
  await page.addInitScript((saved) => {
    sessionStorage.setItem('advertest.wizard.v2', saved)
  }, JSON.stringify(draft))
  await page.goto('/experiments/new')
  await expect(page.getByRole('heading', { name: 'Tấn công', exact: true })).toBeVisible()
  const card = attackCard(page, 'fgsm v1')
  await expect(page.getByLabel('fgsm v1', { exact: true })).toBeChecked()
  await expect(card.getByRole('radio', { name: 'Quét lưới' })).toHaveAttribute(
    'aria-checked',
    'true',
  )
  await expect(card.getByText('2', { exact: true })).toBeVisible()
  await expect(card.getByText('8', { exact: true })).toBeVisible()
  await expect(page.getByRole('switch', { name: 'Dừng sớm khi model đã sụp' })).not.toBeChecked()
  await expect(visibleButton(page, /^Tiếp/)).toBeEnabled()
  await expectNoHorizontalScroll(page)
})
