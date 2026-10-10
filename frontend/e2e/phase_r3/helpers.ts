// Tiện ích cho kịch bản E2E Phase R3: backend thật, worker CPU thật (`run` và `--tools`), fixture 5
// ảnh của scripts/e2e.sh. Dữ liệu dựng qua API khi bước đó không phải đối tượng của kịch bản.
// Nhãn, role và data-testid dùng ở đây là interface ghi ở requirements.md Phase R3, mục
// "Chốt ở Group 0" (Interface cho test nghiệm thu).
import { expect, type Page } from '@playwright/test'

import { fixtureIds } from '../phase_05/helpers'
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
