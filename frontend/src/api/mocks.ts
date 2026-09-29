/**
 * Dữ liệu mock đọc từ contracts/mocks (đã được validate theo schema trong CI).
 * Chỉ được nạp khi VITE_USE_MOCKS=true.
 */
import type { HealthResponse, Me, RunResultOutput as RunResult } from '@/contracts/api'

const files = import.meta.glob<unknown>('../../../contracts/mocks/**/*.json', {
  eager: true,
  import: 'default',
})

/** Mọi mock của một schema, theo tên thư mục trong contracts/mocks (ví dụ `run_result`). */
export function listMocks<T>(schema: string): T[] {
  const prefix = `../../../contracts/mocks/${schema}/`
  return Object.entries(files)
    .filter(([file]) => file.startsWith(prefix))
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([, data]) => data as T)
}

export function mockGet(path: string): unknown {
  if (path === '/health') {
    const ok = listMocks<HealthResponse>('health_response').find((h) => h.status === 'ok')
    if (ok) return ok
  }
  if (path === '/auth/me') return mockMe()
  const run = /^\/runs\/([0-9a-f-]{36})$/.exec(path)
  if (run) {
    const found = listMocks<RunResult>('run_result').find((r) => r.run_id === run[1])
    if (found) return found
  }
  throw new Error(`Không có mock cho GET ${path}`)
}

/** Người dùng của chế độ mock: mock `me/<VITE_MOCK_ME>.json`, mặc định `admin`. */
export function mockMe(name: string = import.meta.env.VITE_MOCK_ME ?? 'admin'): Me {
  const prefix = '../../../contracts/mocks/me/'
  const found = files[`${prefix}${name}.json`]
  if (!found) throw new Error(`Không có mock me/${name}.json`)
  return found as Me
}

/** Chế độ mock không ghi được gì: request thay đổi dữ liệu báo lỗi rõ ràng. */
export function mockSend(method: string, path: string): never {
  throw new Error(`Chế độ mock không hỗ trợ ${method} ${path}`)
}
