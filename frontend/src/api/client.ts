import { toApiError } from './errors'

export { ApiError } from './errors'

/** Tên cookie và header CSRF kiểu double-submit (requirements.md Phase 4). */
export const CSRF_COOKIE = 'csrf_token'
export const CSRF_HEADER = 'X-CSRF-Token'

type Method = 'POST' | 'PUT' | 'PATCH' | 'DELETE'

function apiUrl(path: string): string {
  return `${import.meta.env.VITE_API_BASE_URL ?? ''}${path}`
}

/** Giá trị cookie theo tên; `source` mặc định là `document.cookie` (test truyền chuỗi riêng). */
export function readCookie(name: string, source?: string): string | null {
  const raw = source ?? (typeof document === 'undefined' ? '' : document.cookie)
  for (const part of raw.split(';')) {
    const [key, ...rest] = part.trim().split('=')
    if (key === name) return decodeURIComponent(rest.join('='))
  }
  return null
}

async function parse<T>(response: Response): Promise<T> {
  if (response.status === 204) return undefined as T
  const body: unknown = await response.json().catch(() => null)
  if (!response.ok) throw toApiError(response.status, body)
  return body as T
}

/** GET tới backend; ở chế độ mock trả dữ liệu trong contracts/mocks, không gọi mạng. */
export async function apiGet<T>(path: string): Promise<T> {
  // Viết thẳng biểu thức (không qua hàm): bản build thay bằng hằng số và bỏ nhánh mock.
  if (import.meta.env.VITE_USE_MOCKS === 'true') {
    const { mockGet } = await import('./mocks')
    return mockGet(path) as T
  }
  const response = await fetch(apiUrl(path), {
    credentials: 'include',
    headers: { Accept: 'application/json' },
  })
  return parse<T>(response)
}

/** Request thay đổi dữ liệu: gửi cookie và tự thêm `X-CSRF-Token` lấy từ cookie `csrf_token`. */
export async function apiSend<T>(method: Method, path: string, body?: unknown): Promise<T> {
  // Viết thẳng biểu thức (không qua hàm): bản build thay bằng hằng số và bỏ nhánh mock.
  if (import.meta.env.VITE_USE_MOCKS === 'true') {
    const { mockSend } = await import('./mocks')
    return mockSend(method, path)
  }
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  const csrf = readCookie(CSRF_COOKIE)
  if (csrf) headers[CSRF_HEADER] = csrf
  const response = await fetch(apiUrl(path), {
    method,
    credentials: 'include',
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  return parse<T>(response)
}
