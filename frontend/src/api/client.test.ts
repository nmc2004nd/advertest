import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiError, CSRF_COOKIE, CSRF_HEADER, apiGet, apiSend, readCookie } from './client'

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

describe('apiSend', () => {
  it('gửi cookie, body JSON và X-CSRF-Token lấy từ cookie csrf_token', async () => {
    vi.stubEnv('VITE_USE_MOCKS', 'false')
    vi.stubGlobal('document', { cookie: 'khac=1; csrf_token=abc%3D; advertest_session=x' })
    const fetchMock = stubFetch(200, { ok: true })
    await apiSend('POST', '/auth/password', { a: 1 })
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(init).toMatchObject({ method: 'POST', credentials: 'include', body: '{"a":1}' })
    expect(init.headers).toMatchObject({ [CSRF_HEADER]: 'abc=' })
  })

  it('204 trả undefined', async () => {
    vi.stubEnv('VITE_USE_MOCKS', 'false')
    vi.stubGlobal('document', { cookie: '' })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })))
    await expect(apiSend('POST', '/auth/logout')).resolves.toBeUndefined()
  })

  it('lỗi 401 thành ApiError unauthenticated', async () => {
    vi.stubEnv('VITE_USE_MOCKS', 'false')
    vi.stubGlobal('document', { cookie: '' })
    stubFetch(401, { schema_version: 1, error: { code: 'unauthenticated', message: 'x' } })
    await expect(apiSend('POST', '/auth/logout')).rejects.toMatchObject({
      status: 401,
      code: 'unauthenticated',
    })
  })
})

describe('readCookie', () => {
  it('đọc đúng cookie theo tên', () => {
    expect(readCookie(CSRF_COOKIE, 'a=1; csrf_token=xyz')).toBe('xyz')
    expect(readCookie(CSRF_COOKIE, 'a=1')).toBeNull()
  })
})
