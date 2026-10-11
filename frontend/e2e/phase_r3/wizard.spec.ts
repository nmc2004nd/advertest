// validation.md Phase R3, Group 5 — Wizard 3 bước (M2):
// - đúng 3 bước: Mục đích, Model và dữ liệu, Attack và xác nhận;
// - experiment Khám phá tạo được chỉ với lựa chọn mặc định cộng chọn model, slice, máy chạy;
// - không có ô số tự do ngoài "Tùy chỉnh nâng cao";
// - attack của experiment tạo qua wizard bằng attack của `POST /experiments/draft` cùng lựa chọn;
// - Chính thức: attack và level bắt buộc của protocol bị khóa.
// Máy chạy `e2e-offline` (không có worker): experiment chỉ cần được tạo, không cần chạy.
import { expect, type Page, test } from '@playwright/test'

import { expectNoHorizontalScroll } from '../phase_04/helpers'
import { cancelExperiment, fixtureIds, visibleButton } from '../phase_05/helpers'
import { createProtocolApi, userPage } from '../phase_08/helpers'
import { chooseOption, DEV_OPEN, getJson, postJson, PROTOCOL_LEVELS, SERVER_WAIT } from './helpers'

const STEPS = ['Mục đích', 'Model và dữ liệu', 'Attack và xác nhận']

test.setTimeout(120_000)

type Attack = { attack_spec_id: string; grid: { levels: number[] } | null }
type Detail = { id: string; protocol: { id: string }; config: { attacks: Attack[] } }

const next = (page: Page) => visibleButton(page, /^Tiếp/).click()

async function stepTwo(page: Page) {
  await chooseOption(page, 'Model', 'yolov8n-coco')
  await chooseOption(page, 'Dataset và slice', /5 ảnh/)
  await chooseOption(page, 'Máy chạy', 'e2e-offline')
}

function byAttack(attacks: Attack[]) {
  return Object.fromEntries(attacks.map((a) => [a.attack_spec_id, a.grid?.levels ?? null]))
}

test('Khám phá trong 3 bước, bằng bản nháp của backend', async ({ browser }, info) => {
  const { page } = await userPage(browser, info, ['engineer'])
  await page.goto('/experiments/new')
  await expect(page.getByTestId('wizard-step')).toHaveText(STEPS)

  await page
    .getByRole('radiogroup', { name: 'Mode' })
    .getByRole('radio', { name: /Khám phá/ })
    .check()
  await page
    .getByRole('radiogroup', { name: 'Preset' })
    .getByRole('radio', { name: /Nhanh/ })
    .check()
  await next(page)
  await stepTwo(page)
  await next(page)

  await expect(page.getByTestId('attack-row').first()).toBeVisible({ timeout: SERVER_WAIT })
  const numbers = page.locator('input[type="number"]:visible')
  for (const input of await numbers.all()) {
    await expect(input.locator('xpath=ancestor::details')).toHaveCount(1)
  }
  await expectNoHorizontalScroll(page)
  await visibleButton(page, 'Tạo experiment').click()
  await expect(page).toHaveURL(/\/experiments\/[0-9a-f-]{36}$/)
  await expect(page.getByTestId('experiment-mode')).toHaveText(/Khám phá/)

  const id = page.url().split('/').pop() ?? ''
  const created = await getJson<Detail>(page, `/experiments/${id}`)
  expect(created.protocol.id).toBe(DEV_OPEN)
  const ids = await fixtureIds(page, 'e2e-offline')
  const draft = await postJson<{ config: { attacks: Attack[] } }>(page, '/experiments/draft', {
    protocol_id: DEV_OPEN,
    preset: 'fast',
    model_version_id: ids.modelId,
    slice_id: ids.sliceId,
    class_mapping_id: ids.mappingId,
    compute_target_id: ids.targetId,
    attack_spec_ids: null,
    limit: { kind: 'time', value: '7200' },
    training_slice_id: null,
  })
  expect(byAttack(created.config.attacks)).toEqual(byAttack(draft.config.attacks))
  await cancelExperiment(page, id)
})

test('Chính thức: attack và level bắt buộc bị khóa', async ({ browser }, info) => {
  const reviewer = await userPage(browser, info, ['reviewer'])
  const protocol = await createProtocolApi(reviewer.page, PROTOCOL_LEVELS)
  const { page } = await userPage(browser, info, ['engineer'])
  await page.goto('/experiments/new')
  await page
    .getByRole('radiogroup', { name: 'Mode' })
    .getByRole('radio', { name: /Chính thức/ })
    .check()
  const protocolName = (await getJson<{ name: string }>(page, `/protocols/${protocol.id}`)).name
  await chooseOption(page, 'Protocol', protocolName)
  await page
    .getByRole('radiogroup', { name: 'Preset' })
    .getByRole('radio', { name: /Tiêu chuẩn/ })
    .check()
  await next(page)
  await stepTwo(page)
  await next(page)

  const fgsm = page.locator('[data-testid="attack-row"][data-attack="fgsm"]')
  await expect(fgsm).toBeVisible({ timeout: SERVER_WAIT })
  await expect(fgsm.getByText('Protocol yêu cầu')).toBeVisible()
  for (const level of PROTOCOL_LEVELS) {
    await expect(fgsm.locator(`[data-level="${level}"]`)).toHaveAttribute('aria-disabled', 'true')
  }
  await expect(fgsm.getByRole('button', { name: /Bỏ attack/ })).toHaveCount(0)
})
