// Tiện ích cho kịch bản E2E Phase 5: backend thật, worker CPU thật và dữ liệu fixture do
// scripts/e2e.sh dựng (5 ảnh KITTI, YOLOv8n, máy local-dev, DEV_ALLOW_UNBLURRED=true).
import { expect, type APIRequestContext, type Locator, type Page } from '@playwright/test'

/** Thời gian chờ worker CPU chạy xong (lần đầu có calibration; sau đó trúng cache). */
export const WORKER_TIMEOUT = 240_000

async function json<T>(request: APIRequestContext, path: string): Promise<T> {
  const response = await request.get(`/api${path}`)
  expect(response.status(), path).toBe(200)
  return (await response.json()) as T
}

interface Named {
  id: string
  name: string
}

/** Id của tài nguyên fixture (qua API, bằng phiên của trang đã đăng nhập). */
export async function fixtureIds(page: Page) {
  const request = page.request
  const models = await json<(Named & { framework: string })[]>(request, '/models')
  const model = models.find((m) => m.name === 'yolov8n-coco')
  expect(model).toBeTruthy()
  const slices = await json<(Named & { dataset_version_id: string; size: number })[]>(
    request,
    '/slices',
  )
  const slice = slices.find((s) => s.size === 5)
  expect(slice).toBeTruthy()
  const mappings = await json<Named[]>(
    request,
    `/class-mappings?dataset_version=${slice?.dataset_version_id}&model=${model?.id}`,
  )
  const targets = await json<Named[]>(request, '/compute-targets')
  const target = targets.find((t) => t.name === 'local-dev')
  const specs = await json<(Named & { spec_sha256: string })[]>(request, '/attack-specs')
  return {
    modelId: model?.id ?? '',
    sliceId: slice?.id ?? '',
    mappingId: mappings[0]?.id ?? '',
    targetId: target?.id ?? '',
    spec: (name: string) => {
      const spec = specs.find((s) => s.name === name)
      expect(spec, name).toBeTruthy()
      return spec as Named & { spec_sha256: string }
    },
  }
}

/** Tạo experiment qua API (CSRF từ cookie của trang); trả id. */
export async function createExperiment(page: Page, attacks: [string, number[]][]): Promise<string> {
  const ids = await fixtureIds(page)
  const csrf = (await page.context().cookies()).find((c) => c.name === 'csrf_token')?.value ?? ''
  const response = await page.request.post('/api/experiments', {
    headers: { 'X-CSRF-Token': csrf },
    data: {
      schema_version: 1,
      protocol_id: '2edcdef5-0d3a-5d5f-98ac-b02637fa6718',
      model_version_id: ids.modelId,
      slice_id: ids.sliceId,
      class_mapping_id: ids.mappingId,
      compute_target_id: ids.targetId,
      attacks: attacks.map(([name, levels]) => ({
        schema_version: 1,
        attack_spec_id: ids.spec(name).id,
        spec_sha256: ids.spec(name).spec_sha256,
        mode: 'grid',
        grid: { levels },
        search: null,
        seed: 0,
      })),
      limit: { kind: 'time', value: '7200' },
    },
  })
  expect(response.status(), await response.text()).toBe(201)
  return ((await response.json()) as { id: string }).id
}

/** Nút đang hiển thị (desktop và điện thoại có bản riêng của cùng một nút). */
export function visibleButton(page: Page, name: RegExp | string): Locator {
  return page.getByRole('button', { name }).filter({ visible: true }).first()
}

/** Khối của một attack ở bước 4 (theo nhãn ô chọn, ví dụ "fgsm v1"). */
export function attackCard(page: Page, label: string): Locator {
  return page.locator('div.rounded-lg.border', { has: page.getByLabel(label, { exact: true }) })
}

export async function addLevel(card: Locator, value: string): Promise<void> {
  const input = card.getByLabel(/Thêm level/)
  await input.fill(value)
  await input.press('Enter')
}
