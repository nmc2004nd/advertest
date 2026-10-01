// Tiện ích cho kịch bản E2E Phase 6: dữ liệu do scripts/e2e.sh dựng (task 36a): slice đánh giá 3
// ảnh, slice huấn luyện 2 ảnh không giao, `adv_patch` max_iter = 4, worker CPU thật cho local-dev.
import { expect, type APIRequestContext, type Page } from '@playwright/test'

export const RUN_TIMEOUT = 420_000

interface Named {
  id: string
  name: string
}

async function json<T>(request: APIRequestContext, path: string): Promise<T> {
  const response = await request.get(`/api${path}`)
  expect(response.status(), path).toBe(200)
  return (await response.json()) as T
}

/** Id của tài nguyên Phase 6 (qua API bằng phiên của trang đã đăng nhập). */
export async function phase06Ids(page: Page) {
  const request = page.request
  const models = await json<Named[]>(request, '/models')
  const model = models.find((m) => m.name === 'yolov8n-coco')
  expect(model).toBeTruthy()
  const slices = await json<(Named & { dataset_version_id: string; size: number })[]>(
    request,
    '/slices',
  )
  const evaluation = slices.find((s) => s.size === 3)
  const training = slices.find((s) => s.size === 2)
  expect(evaluation && training).toBeTruthy()
  const mappings = await json<Named[]>(
    request,
    `/class-mappings?dataset_version=${evaluation?.dataset_version_id}&model=${model?.id}`,
  )
  const targets = await json<Named[]>(request, '/compute-targets')
  const target = targets.find((t) => t.name === 'local-dev')
  const specs = await json<(Named & { spec_sha256: string })[]>(request, '/attack-specs')
  return {
    modelId: model?.id ?? '',
    evaluationId: evaluation?.id ?? '',
    trainingId: training?.id ?? '',
    mappingId: mappings[0]?.id ?? '',
    targetId: target?.id ?? '',
    specs,
  }
}

async function csrfToken(page: Page): Promise<string> {
  return (await page.context().cookies()).find((c) => c.name === 'csrf_token')?.value ?? ''
}

/** Tạo experiment trên slice đánh giá 3 ảnh qua API; attack cần train dùng slice huấn luyện. */
export async function createPhase06Experiment(
  page: Page,
  attacks: [string, number[]][],
): Promise<string> {
  const ids = await phase06Ids(page)
  const spec = (name: string) => {
    const found = ids.specs.find((s) => s.name === name)
    expect(found, name).toBeTruthy()
    return found as Named & { spec_sha256: string }
  }
  const response = await page.request.post('/api/experiments', {
    headers: { 'X-CSRF-Token': await csrfToken(page) },
    data: {
      schema_version: 1,
      protocol_id: '2edcdef5-0d3a-5d5f-98ac-b02637fa6718',
      model_version_id: ids.modelId,
      slice_id: ids.evaluationId,
      class_mapping_id: ids.mappingId,
      compute_target_id: ids.targetId,
      attacks: attacks.map(([name, levels]) => ({
        schema_version: 1,
        attack_spec_id: spec(name).id,
        spec_sha256: spec(name).spec_sha256,
        mode: 'grid',
        grid: { levels },
        search: null,
        seed: 0,
        ...(name === 'adv_patch' ? { training_slice_id: ids.trainingId } : {}),
      })),
      limit: { kind: 'time', value: '7200' },
    },
  })
  expect(response.status(), await response.text()).toBe(201)
  return ((await response.json()) as { id: string }).id
}

/** Chờ experiment chạy xong (worker thật). */
export async function waitCompleted(page: Page, id: string): Promise<void> {
  await expect
    .poll(
      async () => {
        const response = await page.request.get(`/api/experiments/${id}`)
        return ((await response.json()) as { status: string }).status
      },
      { timeout: RUN_TIMEOUT, intervals: [2000] },
    )
    .toBe('completed')
}

/** Toàn catalog với level rút gọn (mỗi attack 2 level để có diện tích xếp hạng). */
export const REDUCED_CATALOG: [string, number[]][] = [
  ['fgsm', [2, 8]],
  ['pgd_linf', [2, 8]],
  ['pgd_l2', [1, 4]],
  ['fog', [1, 3]],
  ['snow', [1, 3]],
  ['frost', [1, 3]],
  ['motion_blur', [1, 3]],
  ['contrast', [1, 3]],
  ['bbox_occlusion', [0.3, 0.9]],
  ['adv_patch', [0.05, 0.1]],
]
