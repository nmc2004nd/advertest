// validation.md Phase R3, Group 6 — Đăng ký model qua web (M7), worker công cụ thật:
// - form ONNX nêu hai layout đầu ra được hỗ trợ;
// - file pickle khác (.pkl) bị chặn ở client, không gọi API upload; file `.pt` hiện panel chuyển
//   sang safetensors trong sandbox (đề xuất contract 003) và chưa upload cho tới khi bấm chuyển;
// - model `check_failed` có nút "Kiểm tra lại", bấm thì về "Đang kiểm tra".
import { expect, test } from '@playwright/test'

import { visibleButton } from '../phase_05/helpers'
import { userPage } from '../phase_08/helpers'
import { chooseOption, countRequests, getJson, postJson, WORKER_TIMEOUT } from './helpers'

test.setTimeout(WORKER_TIMEOUT + 60_000)

test('form đăng ký: layout ONNX, chặn file pickle, .pt đi qua sandbox', async ({
  browser,
}, info) => {
  const { page } = await userPage(browser, info, ['admin'])
  const uploads = countRequests(page, /\/api\/models\/uploads$/)
  await page.goto('/models')
  await visibleButton(page, 'Đăng ký model').click()
  await chooseOption(page, 'Framework', /onnx/i)
  await expect(page.getByTestId('onnx-layouts')).toContainText('boxes/scores/labels')
  await expect(page.getByTestId('onnx-layouts')).toContainText('(1, 4+C, N)')

  await page.getByLabel('File weights', { exact: true }).setInputFiles({
    name: 'model.pkl',
    mimeType: 'application/octet-stream',
    buffer: Buffer.from('khong phai onnx'),
  })
  await expect(page.getByRole('alert')).toContainText('.onnx')
  await expect(page.getByRole('button', { name: 'Đăng ký', exact: true })).toBeDisabled()

  await page.getByLabel('File weights', { exact: true }).setInputFiles({
    name: 'best.pt',
    mimeType: 'application/octet-stream',
    buffer: Buffer.from('pickle gia'),
  })
  await expect(page.getByTestId('convert-panel')).toContainText('sandbox')
  await expect(page.getByRole('button', { name: 'Chuyển sang safetensors' })).toBeEnabled()
  expect(uploads()).toBe(0)
})

test('model kiểm tra không đạt có nút kiểm tra lại', async ({ browser }, info) => {
  const { page } = await userPage(browser, info, ['admin'])
  const content = Buffer.from(`khong phai onnx ${Date.now()} ${Math.random()}`)
  const upload = await postJson<{ upload_id: string; url: string }>(page, '/models/uploads', {
    filename: 'hong.onnx',
    size_bytes: content.length,
  })
  const put = await page.request.put(upload.url, { data: content })
  expect(put.status()).toBe(200)
  const model = await postJson<{ id: string }>(page, '/models', {
    name: `onnx-hong-${Date.now()}`,
    framework: 'onnx',
    architecture: 'tệp hỏng cho E2E',
    upload_id: upload.upload_id,
    class_names: ['person', 'car'],
    input_size: 640,
  })
  await expect
    .poll(async () => (await getJson<{ status: string }>(page, `/models/${model.id}`)).status, {
      timeout: WORKER_TIMEOUT,
      intervals: [1000],
    })
    .toBe('check_failed')

  await page.goto(`/models/${model.id}`)
  await expect(page.getByTestId('model-status')).toHaveText(/Kiểm tra không đạt/)
  await expect(page.getByTestId('model-check')).not.toBeEmpty()
  await visibleButton(page, 'Kiểm tra lại').click()
  await expect(page.getByTestId('model-status')).toHaveText(/Đang kiểm tra|Kiểm tra không đạt/)
  expect((await getJson<{ status: string }>(page, `/models/${model.id}`)).status).not.toBe('ready')
})
