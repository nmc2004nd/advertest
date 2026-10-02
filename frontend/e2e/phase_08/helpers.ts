// Tiện ích cho kịch bản E2E Phase 8: backend thật, worker CPU thật, fixture 5 ảnh của scripts/e2e.sh.
// Thiết lập dữ liệu qua API khi bước đó không phải đối tượng của kịch bản; bước đang kiểm tra đi
// qua giao diện.
import { type Browser, expect, type Page, type TestInfo } from '@playwright/test'

import { activeUser, loginUi } from '../phase_04/helpers'
import { fixtureIds, WORKER_TIMEOUT } from '../phase_05/helpers'

export { WORKER_TIMEOUT }

/** Level FGSM riêng cho từng viewport: worker chạy thật (không trúng cache của viewport trước), có
 * failure case để review. Mức sụt mAP@0.5 của FGSM trên fixture từ eps 1 trở lên đều đáng kể. */
export const LEVELS: Record<string, [number, number]> = {
  phone: [1, 2],
  tablet: [3, 4],
  desktop: [5, 6],
}

export async function csrf(page: Page): Promise<Record<string, string>> {
  const token = (await page.context().cookies()).find((c) => c.name === 'csrf_token')?.value
  return { 'X-CSRF-Token': token ?? '' }
}

async function postJson<T>(page: Page, path: string, data?: unknown): Promise<T> {
  const response = await page.request.post(`/api${path}`, { data, headers: await csrf(page) })
  expect(response.status(), `${path}: ${await response.text()}`).toBeLessThan(300)
  return (await response.json()) as T
}

async function getJson<T>(page: Page, path: string): Promise<T> {
  const response = await page.request.get(`/api${path}`)
  expect(response.status(), path).toBe(200)
  return (await response.json()) as T
}

/** Trang mới (context riêng) đã đăng nhập bằng người dùng mới có `roles`. */
export async function userPage(
  browser: Browser,
  info: TestInfo,
  roles: string[],
): Promise<{ page: Page; email: string }> {
  const context = await browser.newContext({
    baseURL: info.project.use.baseURL,
    viewport: info.project.use.viewport,
    isMobile: info.project.use.isMobile,
    hasTouch: info.project.use.hasTouch,
    acceptDownloads: true,
  })
  const page = await context.newPage()
  const email = await activeUser(page.request, info, roles)
  await loginUi(page, email)
  return { page, email }
}

/** Protocol FGSM quét lưới `levels`, tiêu chí sụt tối đa 95% ở level lớn (đạt). Không cấm code
 * chưa commit: worker E2E chạy từ working tree của máy dev. */
export async function createProtocolApi(page: Page, levels: number[]): Promise<{ id: string }> {
  // Reviewer không có quyền xem compute target: chỉ đọc catalog để lấy hash của spec.
  const specs = await getJson<{ name: string; spec_sha256: string }[]>(page, '/attack-specs')
  const fgsm = specs.find((s) => s.name === 'fgsm')
  expect(fgsm).toBeTruthy()
  const body = {
    description: 'Protocol E2E Phase 8',
    required_attacks: [
      {
        attack_spec_name: 'fgsm',
        spec_sha256: fgsm?.spec_sha256,
        mode: 'grid',
        grid: { levels },
      },
    ],
    min_slice_size: 5,
    pass_criteria: [
      {
        kind: 'max_drop_at_level',
        attack_spec_name: 'fgsm',
        level: levels[levels.length - 1],
        threshold_kind: 'relative_drop',
        threshold: 0.95,
        class_filter: null,
      },
    ],
    cases_to_review_per_attack: 2,
    forbid_dirty_runs: false,
  }
  const name = `e2e-p8-${Date.now()}-${Math.floor(Math.random() * 1e6)}`
  return postJson(page, '/protocols', { name, body })
}

export async function createExperimentApi(
  page: Page,
  protocolId: string,
  levels: number[],
): Promise<string> {
  const ids = await fixtureIds(page)
  const created = await postJson<{ id: string }>(page, '/experiments', {
    schema_version: 1,
    protocol_id: protocolId,
    model_version_id: ids.modelId,
    slice_id: ids.sliceId,
    class_mapping_id: ids.mappingId,
    compute_target_id: ids.targetId,
    attacks: [
      {
        attack_spec_id: ids.spec('fgsm').id,
        spec_sha256: ids.spec('fgsm').spec_sha256,
        mode: 'grid',
        grid: { levels },
        seed: 0,
      },
    ],
    limit: { kind: 'time', value: '7200' },
  })
  return created.id
}

export async function waitStatus(page: Page, id: string, status: string): Promise<void> {
  await expect
    .poll(async () => (await getJson<{ status: string }>(page, `/experiments/${id}`)).status, {
      timeout: WORKER_TIMEOUT,
      intervals: [1000],
    })
    .toBe(status)
}

export async function submitApi(page: Page, id: string): Promise<void> {
  await postJson(page, `/experiments/${id}/submit`, {})
}

export async function claimApi(page: Page, id: string): Promise<void> {
  await postJson(page, `/reviews/${id}/claim`)
}

export async function reviewAllApi(page: Page, id: string): Promise<void> {
  const detail = await getJson<{ review: { required_cases: { failure_case_id: string }[] } }>(
    page,
    `/experiments/${id}`,
  )
  for (const c of detail.review.required_cases) {
    await postJson(page, `/reviews/${id}/cases/${c.failure_case_id}/verdicts`, {
      severity: 'minor',
      kind: 'acceptable',
      mitigation: null,
    })
  }
}

export const APPROVE = {
  decision: 'approve',
  model_verdict: 'meets_criteria',
  conclusion: 'Bài test đúng protocol.',
  mitigation: 'Theo dõi FGSM ở eps lớn hơn.',
}

export async function decideApi(page: Page, id: string, body: object): Promise<void> {
  await postJson(page, `/reviews/${id}/decision`, body)
}

/** Report `ready` của experiment đã chấp nhận (sinh nền sau quyết định). */
export async function readyReportId(page: Page, id: string): Promise<string> {
  let reportId = ''
  await expect
    .poll(
      async () => {
        const detail = await getJson<{ report: { id: string; status: string } | null }>(
          page,
          `/experiments/${id}`,
        )
        reportId = detail.report?.id ?? ''
        return detail.report?.status
      },
      { timeout: 120_000, intervals: [1000] },
    )
    .toBe('ready')
  return reportId
}

/** Vuốt ngang trên trình xem case (điện thoại): `left` sang case sau. */
export async function swipe(page: Page, direction: 'left' | 'right'): Promise<void> {
  await page
    .locator('[data-swipe="true"]')
    .first()
    .evaluate((element, dir) => {
      const box = element.getBoundingClientRect()
      const y = box.top + box.height / 2
      const [from, to] =
        dir === 'left' ? [box.right - 20, box.left + 20] : [box.left + 20, box.right - 20]
      const touch = (x: number) =>
        new Touch({ identifier: 1, target: element, clientX: x, clientY: y })
      element.dispatchEvent(
        new TouchEvent('touchstart', {
          bubbles: true,
          touches: [touch(from)],
          changedTouches: [touch(from)],
        }),
      )
      element.dispatchEvent(
        new TouchEvent('touchend', { bubbles: true, touches: [], changedTouches: [touch(to)] }),
      )
    }, direction)
}
