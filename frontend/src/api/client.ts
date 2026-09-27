import { toApiError } from './errors'

export { ApiError } from './errors'

function mocksEnabled(): boolean {
  return import.meta.env.VITE_USE_MOCKS === 'true'
}

/** GET tới backend; ở chế độ mock trả dữ liệu trong contracts/mocks, không gọi mạng. */
export async function apiGet<T>(path: string): Promise<T> {
  if (mocksEnabled()) {
    const { mockGet } = await import('./mocks')
    return mockGet(path) as T
  }
  const base = import.meta.env.VITE_API_BASE_URL ?? ''
  const response = await fetch(`${base}${path}`, {
    credentials: 'include',
    headers: { Accept: 'application/json' },
  })
  const body: unknown = await response.json().catch(() => null)
  if (!response.ok) throw toApiError(response.status, body)
  return body as T
}
