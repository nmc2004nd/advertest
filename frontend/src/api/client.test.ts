import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiError, apiGet } from './client'

function stubFetch(status: number, body: unknown) {
  const fetchMock = vi
    .fn()
    .mockResolvedValue(
      new Response(typeof body === 'string' ? body : JSON.stringify(body), { status }),
    )
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
})

describe('apiGet', () => {
  it('trả JSON khi thành công, gửi kèm cookie', async () => {
    vi.stubEnv('VITE_USE_MOCKS', 'false')
    const fetchMock = stubFetch(200, { status: 'ok' })
    await expect(apiGet('/health')).resolves.toEqual({ status: 'ok' })
    expect(fetchMock).toHaveBeenCalledWith(
      '/health',
      expect.objectContaining({ credentials: 'include' }),
    )
  })

  it('đọc body ErrorResponse thành ApiError', async () => {
    vi.stubEnv('VITE_USE_MOCKS', 'false')
    stubFetch(501, { schema_version: 1, error: { code: 'not_implemented', message: 'Chưa có' } })
    const error = await apiGet('/users').catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 501, code: 'not_implemented', message: 'Chưa có' })
  })

  it('body lỗi không theo định dạng thì code = unknown', async () => {
    vi.stubEnv('VITE_USE_MOCKS', 'false')
    stubFetch(502, 'Bad Gateway')
    await expect(apiGet('/users')).rejects.toMatchObject({ status: 502, code: 'unknown' })
  })

  it('chế độ mock không gọi mạng', async () => {
    vi.stubEnv('VITE_USE_MOCKS', 'true')
    const fetchMock = stubFetch(500, null)
    await expect(apiGet('/health')).resolves.toMatchObject({ status: 'ok' })
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
