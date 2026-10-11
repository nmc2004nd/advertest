// Tiện ích cho kịch bản E2E Phase R3: backend thật, worker CPU thật (`run` và `--tools`), fixture 5
// ảnh của scripts/e2e.sh. Dữ liệu dựng qua API khi bước đó không phải đối tượng của kịch bản.
// Nhãn, role và data-testid dùng ở đây là interface ghi ở requirements.md Phase R3, mục
// "Chốt ở Group 0" (Interface cho test nghiệm thu).
import { expect, type Locator, type Page } from '@playwright/test'

import { fixtureIds, visibleButton } from '../phase_05/helpers'
import { csrf, WORKER_TIMEOUT } from '../phase_08/helpers'

export { WORKER_TIMEOUT }

/** Protocol `dev-open` (seed migration 0002): experiment Khám phá. */
export const DEV_OPEN = '2edcdef5-0d3a-5d5f-98ac-b02637fa6718'

export async function postJson<T>(page: Page, path: string, data?: unknown): Promise<T> {
  const response = await page.request.post(`/api${path}`, { data, headers: await csrf(page) })
  expect(response.status(), `${path}: ${await response.text()}`).toBeLessThan(300)
  return (await response.json()) as T
}

export async function getJson<T>(page: Page, path: string): Promise<T> {
  const response = await page.request.get(`/api${path}`)
  expect(response.status(), path).toBe(200)
  return (await response.json()) as T
}

/** Experiment qua API (protocol mặc định `dev-open`), attack FGSM quét lưới `levels`. */
export async function experimentApi(
  page: Page,
  levels: number[],
  protocolId: string = DEV_OPEN,
): Promise<string> {
  const ids = await fixtureIds(page)
  const fgsm = ids.spec('fgsm')
  const created = await postJson<{ id: string }>(page, '/experiments', {
    schema_version: 1,
    protocol_id: protocolId,
    model_version_id: ids.modelId,
    slice_id: ids.sliceId,
    class_mapping_id: ids.mappingId,
    compute_target_id: ids.targetId,
    attacks: [
      {
        attack_spec_id: fgsm.id,
        spec_sha256: fgsm.spec_sha256,
        mode: 'grid',
        grid: { levels },
        seed: 0,
      },
    ],
    limit: { kind: 'time', value: '7200' },
  })
  return created.id
}

/** Bước của thanh vòng đời: `data-step` → `data-state`. */
export async function lifecycle(page: Page): Promise<Record<string, string>> {
  const steps = page.getByTestId('lifecycle').getByTestId('lifecycle-step')
  await expect(steps.first()).toBeVisible()
  const result: Record<string, string> = {}
  for (const step of await steps.all()) {
    result[(await step.getAttribute('data-step')) ?? ''] =
      (await step.getAttribute('data-state')) ?? ''
  }
  return result
}

/** Số request tới `/api` có đường dẫn khớp `pattern` từ lúc gọi tới lúc gọi hàm trả về. */
export function countRequests(page: Page, pattern: RegExp): () => number {
  let count = 0
  page.on('request', (request) => {
    if (pattern.test(new URL(request.url()).pathname)) count += 1
  })
  return () => count
}

/** Chọn mục `option` của ô chọn có nhãn `label`: `<select>` gốc hoặc combobox/listbox. */
export async function chooseOption(page: Page, label: string, option: string | RegExp) {
  const control = page.getByLabel(label, { exact: true }).filter({ visible: true }).first()
  if ((await control.evaluate((el) => el.tagName)) === 'SELECT') {
    const options = await control.locator('option').allTextContents()
    const match = options.find((o) =>
      typeof option === 'string' ? o.includes(option) : option.test(o),
    )
    expect(match, `${label}: ${option}`).toBeTruthy()
    await control.selectOption({ label: match ?? '' })
    return
  }
  await control.click()
  await page.getByRole('option', { name: option }).first().click()
}

/** Tên các lựa chọn của ô chọn có nhãn `label`. */
export async function optionNames(page: Page, label: string): Promise<string[]> {
  const control = page.getByLabel(label, { exact: true }).filter({ visible: true }).first()
  if ((await control.evaluate((el) => el.tagName)) === 'SELECT') {
    return control.locator('option').allTextContents()
  }
  await control.click()
  const names = await page.getByRole('option').allTextContents()
  await page.keyboard.press('Escape')
  return names
}

/** Ô `<option>` đang chọn của ô chọn có nhãn `label` (`<select>` gốc). */
export function selectedOption(page: Page, label: string): Locator {
  return page
    .getByLabel(label, { exact: true })
    .filter({ visible: true })
    .first()
    .locator('option:checked')
}

export const nextStep = (page: Page) => visibleButton(page, /^Tiếp/).click()

/**
 * Wizard 3 bước (Phase R3) qua bước 1–2, dừng ở bước 3 khi danh sách attack đã hiện. Dùng cho E2E
 * cũ đi qua wizard (plan.md task 23a): `official` là tên protocol chính thức (bỏ trống: Khám phá).
 */
export async function wizardToAttacks(
  page: Page,
  {
    official,
    preset = /Nhanh/,
    slice = /5 ảnh/,
    target,
    onPurpose,
    beforeNext,
  }: {
    official?: string
    preset?: string | RegExp
    slice?: string | RegExp
    target?: string
    /** Gọi ở bước 1 ngay trước khi sang bước 2. */
    onPurpose?: () => Promise<void>
    /** Gọi ở bước 2 ngay trước khi sang bước 3. */
    beforeNext?: () => Promise<void>
  } = {},
): Promise<void> {
  await page.goto('/experiments/new')
  await expect(page.getByTestId('wizard-step')).toHaveCount(3)
  const mode = page.getByRole('radiogroup', { name: 'Mode' })
  if (official) {
    await mode.getByRole('radio', { name: /Chính thức/ }).check()
    await chooseOption(page, 'Protocol', official)
  } else {
    await mode.getByRole('radio', { name: /Khám phá/ }).check()
  }
  await page
    .getByRole('radiogroup', { name: 'Preset' })
    .getByRole('radio', { name: preset })
    .check()
  if (onPurpose) await onPurpose()
  await nextStep(page)
  await chooseOption(page, 'Model', 'yolov8n-coco')
  await chooseOption(page, 'Dataset và slice', slice)
  if (target) await chooseOption(page, 'Máy chạy', target)
  if (beforeNext) await beforeNext()
  await nextStep(page)
  await expect(page.getByTestId('attack-row').first()).toBeVisible()
}

/** Dòng attack ở bước 3 theo tên spec. */
export function attackRow(page: Page, name: string): Locator {
  return page.locator(`[data-testid="attack-row"][data-attack="${name}"]`)
}

/** Bật/tắt chip level của một dòng attack để level đang chọn đúng bằng `levels`. */
export async function setLevels(row: Locator, levels: number[]): Promise<void> {
  // Chip theo giá trị, không theo vị trí: tắt một level ngoài bộ gợi ý thì chip đó biến mất.
  const values = await row
    .locator('[data-level]')
    .evaluateAll((els) => els.map((el) => el.getAttribute('data-level') ?? ''))
  for (const value of values) {
    const chip = row.locator(`[data-level="${value}"]`)
    if ((await chip.count()) === 0) continue
    const want = levels.includes(Number(value))
    if (((await chip.getAttribute('aria-pressed')) === 'true') !== want) await chip.click()
  }
  for (const level of levels) {
    await expect(row.locator(`[data-level="${level}"]`)).toHaveAttribute('aria-pressed', 'true')
  }
  await expect(row.locator('[data-level][aria-pressed="true"]')).toHaveCount(levels.length)
}

/** Bước 3: chỉ giữ các attack trong `wanted` (bỏ attack khác), mỗi attack đúng các level đó. */
export async function keepAttacks(page: Page, wanted: Record<string, number[]>): Promise<void> {
  const rows = page.getByTestId('attack-row')
  const names = await rows.evaluateAll((els) => els.map((el) => el.getAttribute('data-attack')))
  for (const name of names) {
    if (name && !(name in wanted)) {
      await attackRow(page, name)
        .getByRole('button', { name: /^Bỏ attack/ })
        .click()
    }
  }
  await expect(rows).toHaveCount(Object.keys(wanted).length)
  for (const [name, levels] of Object.entries(wanted))
    await setLevels(attackRow(page, name), levels)
}
