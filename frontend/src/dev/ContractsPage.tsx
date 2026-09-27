import { listMocks } from '@/api/mocks'
import { useHealth } from '@/api/queries'
import { StatusBadge } from '@/components/status/StatusBadge'
import type { RunResultOutput as RunResult } from '@/contracts/api'

/** Trang dev: chứng minh type sinh từ contract và mock hoạt động. Không có trong bản production. */
export function ContractsPage() {
  const runs = listMocks<RunResult>('run_result')
  const health = useHealth()
  const mockMode = import.meta.env.VITE_USE_MOCKS === 'true'

  return (
    <main className="mx-auto w-full max-w-3xl space-y-4 p-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
      <header className="space-y-1">
        <h1 className="text-lg font-semibold">Contract và mock (dev)</h1>
        <p className="text-sm text-muted-foreground">
          Chế độ dữ liệu: {mockMode ? 'mock (contracts/mocks)' : 'API thật'} · /health:{' '}
          {health.isPending ? 'đang tải' : health.isError ? 'lỗi' : health.data.status}
        </p>
      </header>

      <ul className="space-y-2">
        {runs.map((run) => (
          <li key={run.run_id} className="min-w-0 rounded-lg border p-3">
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge kind="run" status={run.status} />
              <span className="text-sm">
                Mức {run.level} · {run.progress.images_done}/{run.progress.images_total} ảnh
              </span>
            </div>
            {run.status_reason ? (
              <p className="mt-1 text-sm text-muted-foreground">
                {run.status_reason.code}: {run.status_reason.message}
              </p>
            ) : null}
            <p className="mt-1 font-mono text-xs break-all text-muted-foreground">{run.run_id}</p>
          </li>
        ))}
      </ul>
    </main>
  )
}
