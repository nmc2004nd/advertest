import { Link, useNavigate, useParams, useSearchParams } from 'react-router'

import { useRun } from '@/api/queries'
import { CaseViewer } from '@/components/case-viewer/CaseViewer'
import { LoadError } from '@/components/LoadError'
import { PageLoading } from '@/components/PageLoading'

import { useFailureCase, useFailureCases, useRetryOnImageError } from './api'
import { runLabel } from './format'

/**
 * Trình xem một failure case (`/failure-cases/:id?run=<run_id>`). Case trước/sau lấy theo thứ
 * tự của run (mức nghiêm trọng giảm dần); vuốt trên điện thoại hoặc nút.
 */
export function FailureCasePage() {
  const { id = '' } = useParams()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const view = useFailureCase(id)
  const runId = params.get('run') ?? view.data?.run_id ?? ''
  const run = useRun(runId)
  const siblings = useFailureCases(runId, runId !== '')
  const retry = useRetryOnImageError(() => view.refetch(), view.data?.urls_expire_at)

  if (view.isPending) return <PageLoading />
  if (view.isError) {
    return (
      <div className="p-4 md:p-6">
        <LoadError onRetry={() => void view.refetch()} retrying={view.isFetching} />
      </div>
    )
  }
  const ids = siblings.data?.map((c) => c.id) ?? []
  const index = ids.indexOf(id)
  const goTo = (target: string | undefined) =>
    target ? () => void navigate(`/failure-cases/${target}?run=${runId}`) : undefined

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-4 p-4 md:p-6">
      <header className="flex flex-col gap-1">
        {run.data && (
          <Link
            to={`/experiments/${run.data.experiment_id}?tab=cases`}
            className="text-sm text-muted-foreground hover:underline"
          >
            ← Failure case của experiment
          </Link>
        )}
        <h1 className="text-2xl font-semibold">Failure case {view.data.image_id}</h1>
        <p className="text-sm text-muted-foreground">
          {run.data ? runLabel(run.data) : null}
          {index >= 0 && ` · case ${index + 1}/${ids.length}`}
        </p>
      </header>
      <CaseViewer
        caseView={view.data}
        onPrev={goTo(index > 0 ? ids[index - 1] : undefined)}
        onNext={goTo(index >= 0 && index < ids.length - 1 ? ids[index + 1] : undefined)}
        onImageError={retry}
      />
    </div>
  )
}
