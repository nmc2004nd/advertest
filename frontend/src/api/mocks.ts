/**
 * Dữ liệu mock đọc từ contracts/mocks (đã được validate theo schema trong CI).
 * Chỉ được nạp khi VITE_USE_MOCKS=true.
 */
import type {
  ClassMappingSummary,
  DatasetVersionSummary,
  EstimateResponse,
  ExperimentClone,
  ExperimentDetail,
  ExperimentPage,
  FailureCaseView,
  HealthResponse,
  Manifest,
  Me,
  ModelSummary,
  ProtocolSummary,
  ProtocolView,
  ReviewComment,
  RunResultOutput as RunResult,
  RunView,
  SliceSummary,
} from '@/contracts/api'

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

/** Danh sách mock có trường `field` bằng `value` (bỏ qua khi `value` rỗng). */
function where<T>(schema: string, field: keyof T, value: string | null): T[] {
  const all = listMocks<T>(schema)
  return value ? all.filter((item) => String(item[field]) === value) : all
}

function first<T>(items: T[], path: string): T {
  if (items.length === 0) throw new Error(`Không có mock cho GET ${path}`)
  return items[0]
}

/** Dữ liệu mock cho các GET của Phase 5 (wizard, experiment, run, failure case). */
function mockPhase5(pathname: string, query: URLSearchParams): unknown {
  const id = '([0-9a-f-]{36})'
  const match = (pattern: string) => new RegExp(`^${pattern}$`).exec(pathname)
  const simple: Record<string, string> = {
    '/models': 'model_summary',
    '/datasets': 'dataset_summary',
    '/attack-specs': 'attack_spec',
    '/compute-targets': 'compute_target_public',
  }
  if (pathname in simple) return listMocks(simple[pathname])
  if (pathname === '/protocols') {
    // Phase 8: bản `retired` chỉ có khi `include_retired=true` (như API).
    const all = listMocks<ProtocolSummary>('protocol_summary')
    return query.get('include_retired') === 'true' ? all : all.filter((p) => p.status !== 'retired')
  }
  if (pathname === '/slices') {
    // Phase 6: mock không có danh sách ảnh; coi mọi slice khác là không giao.
    const disjointFrom = query.get('disjoint_from')
    if (disjointFrom)
      return listMocks<SliceSummary>('slice_summary').filter((s) => s.id !== disjointFrom)
    return where<SliceSummary>('slice_summary', 'dataset_version_id', query.get('dataset_version'))
  }
  if (pathname === '/class-mappings') {
    const byVersion = where<ClassMappingSummary>(
      'class_mapping_summary',
      'dataset_version_id',
      query.get('dataset_version'),
    )
    const model = query.get('model')
    return model ? byVersion.filter((m) => m.model_version_id === model) : byVersion
  }
  if (pathname === '/admin/attack-specs') return listMocks('attack_spec_admin_page')[0]
  if (pathname === '/experiments')
    return first(listMocks<ExperimentPage>('experiment_page'), pathname)
  let m = match(`/models/${id}`)
  if (m) return first(where<ModelSummary>('model_summary', 'id', m[1]), pathname)
  m = match(`/dataset-versions/${id}`)
  if (m) return first(where<DatasetVersionSummary>('dataset_version_summary', 'id', m[1]), pathname)
  m = match(`/protocols/${id}`)
  if (m) return first(where<ProtocolView>('protocol_view', 'id', m[1]), pathname)
  m = match(`/experiments/${id}/comments`)
  if (m) return where<ReviewComment>('review_comment', 'experiment_id', m[1])
  m = match(`/experiments/${id}`)
  if (m) return first(where<ExperimentDetail>('experiment_detail', 'id', m[1]), pathname)
  m = match(`/experiments/${id}/runs`)
  if (m) return where<RunView>('run_view', 'experiment_id', m[1])
  m = match(`/experiments/${id}/clone`)
  if (m) {
    const clones = listMocks<ExperimentClone>('experiment_clone')
    return clones.find((c) => c.config.cloned_from === m?.[1]) ?? first(clones, pathname)
  }
  m = match(`/runs/${id}`)
  if (m) {
    const view = where<RunView>('run_view', 'run_id', m[1])
    return view[0] ?? first(where<RunResult>('run_result', 'run_id', m[1]), pathname)
  }
  m = match(`/runs/${id}/manifest`)
  if (m) return first(listMocks<Manifest>('manifest'), pathname)
  m = match(`/runs/${id}/failure-cases`)
  if (m) {
    // Một view mỗi case (mock có nhiều display_mode cho cùng case): ưu tiên bản chỉ có thumbnail.
    const views = where<FailureCaseView>('failure_case_view', 'run_id', m[1])
    const byId = new Map<string, FailureCaseView>()
    for (const view of views) {
      if (!byId.has(view.id) || view.urls.clean === null) byId.set(view.id, view)
    }
    return [...byId.values()].sort((a, b) => b.severity_score - a.severity_score)
  }
  m = match(`/failure-cases/${id}`)
  if (m) return first(where<FailureCaseView>('failure_case_view', 'id', m[1]), pathname)
  throw new Error(`Không có mock cho GET ${pathname}`)
}

export function mockGet(path: string): unknown {
  if (path === '/health') {
    const ok = listMocks<HealthResponse>('health_response').find((h) => h.status === 'ok')
    if (ok) return ok
  }
  if (path === '/auth/me') return mockMe()
  const url = new URL(path, 'http://mock.invalid')
  return mockPhase5(url.pathname, url.searchParams)
}

/** Người dùng của chế độ mock: mock `me/<VITE_MOCK_ME>.json`, mặc định `admin`. */
export function mockMe(name: string = import.meta.env.VITE_MOCK_ME ?? 'admin'): Me {
  const prefix = '../../../contracts/mocks/me/'
  const found = files[`${prefix}${name}.json`]
  if (!found) throw new Error(`Không có mock me/${name}.json`)
  return found as Me
}

/**
 * Chế độ mock không ghi được gì: request thay đổi dữ liệu báo lỗi rõ ràng. Riêng
 * `POST /experiments/estimate` (chỉ tính toán, không tạo gì) trả mock ước lượng để wizard dùng được.
 */
export function mockSend<T>(method: string, path: string): T {
  if (method === 'POST' && path === '/experiments/estimate') {
    const estimate = listMocks<EstimateResponse>('estimate_response')[0]
    if (estimate) return estimate as T
  }
  throw new Error(`Chế độ mock không hỗ trợ ${method} ${path}`)
}
