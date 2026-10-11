import { CircleCheck, CircleX, RotateCw, SearchX } from 'lucide-react'
import type { ReactNode } from 'react'
import { useParams } from 'react-router'

import { ApiError } from '@/api/errors'
import { errorMessage } from '@/api/messages'
import { formatDateTime } from '@/admin/format'
import { useModel, useRecheckModel } from '@/admin/useModelAdmin'
import { TruncatedId } from '@/components/CopyButton'
import { EmptyState } from '@/components/EmptyState'
import { FormAlert } from '@/components/FormAlert'
import { LoadError } from '@/components/LoadError'
import { PageLoading } from '@/components/PageLoading'
import { StatusBadge } from '@/components/status/StatusBadge'
import { Button } from '@/components/ui/button'
import type { ModelSummary } from '@/contracts/api'
import { CATALOG_COPY } from '@/copy/catalog'
import { PageHeader } from '@/layout/PageHeader'

import { OnnxLayouts } from './ModelsPage'

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid gap-1 py-2 sm:grid-cols-[11rem_1fr] sm:gap-3">
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd className="min-w-0 text-sm">{children}</dd>
    </div>
  )
}

function Verdict({ passed, children }: { passed: boolean; children: ReactNode }) {
  const Icon = passed ? CircleCheck : CircleX
  return (
    <span
      className={passed ? 'inline-flex gap-1.5 text-approved' : 'inline-flex gap-1.5 text-fail'}
    >
      <Icon aria-hidden className="mt-0.5 size-4 shrink-0" />
      <span>{children}</span>
    </span>
  )
}

/** `ModelCheckResult`: kết quả kiểm tra gần nhất, cộng kiểm tra gradient (chỉ torchvision). */
function CheckResult({ model }: { model: ModelSummary }) {
  const check = model.check
  if (!check) {
    return (
      <p className="text-sm text-muted-foreground">
        {model.status === 'checking'
          ? 'Worker đang kiểm tra model. Trang tự cập nhật khi có kết quả.'
          : 'Model đăng ký qua CLI, không có kết quả kiểm tra trên web.'}
      </p>
    )
  }
  return (
    <dl className="divide-y divide-border">
      <Row label="Kết quả">
        <Verdict passed={check.passed}>{check.passed ? 'Đạt' : 'Không đạt'}</Verdict>
        {check.details && <span className="mt-1 block break-words">{check.details}</span>}
      </Row>
      <Row label="Gradient">
        {check.gradient_check ? (
          <>
            <Verdict passed={check.gradient_check.passed}>
              {check.gradient_check.passed ? 'Tính được gradient' : 'Không tính được gradient'}
            </Verdict>
            {check.gradient_check.details && (
              <span className="mt-1 block break-words">{check.gradient_check.details}</span>
            )}
          </>
        ) : (
          <span className="text-muted-foreground">
            Không kiểm tra (ONNX không hỗ trợ gradient, hoặc dừng trước bước này).
          </span>
        )}
      </Row>
      <Row label="Kiểm tra lúc">{formatDateTime(check.checked_at)}</Row>
    </dl>
  )
}

function ModelDetail({ model }: { model: ModelSummary }) {
  const recheck = useRecheckModel()
  return (
    <>
      <PageHeader
        back={{ to: '/admin/models', label: 'Model' }}
        eyebrow={model.framework}
        title={model.name}
        actions={
          model.status === 'check_failed' ? (
            <Button disabled={recheck.isPending} onClick={() => recheck.mutate(model.id)}>
              <RotateCw aria-hidden />
              Kiểm tra lại
            </Button>
          ) : undefined
        }
      />
      <div className="flex flex-wrap items-center gap-3">
        <span data-testid="model-status">
          <StatusBadge kind="model" status={model.status} />
        </span>
        {model.status === 'checking' && (
          <span className="text-sm text-muted-foreground">{CATALOG_COPY.checkingNote}</span>
        )}
      </div>
      {recheck.isError && <FormAlert>{errorMessage(recheck.error)}</FormAlert>}
      <div className="grid gap-5 lg:grid-cols-2">
        <section
          className="panel flex flex-col gap-2 p-5"
          aria-label="Kiểm tra model"
          data-testid="model-check"
        >
          <h2 className="text-base font-semibold">Kiểm tra model</h2>
          <CheckResult model={model} />
          {model.framework === 'onnx' && model.status === 'check_failed' && <OnnxLayouts />}
        </section>
        <section className="panel flex flex-col gap-2 p-5" aria-label="Thông tin model">
          <h2 className="text-base font-semibold">Thông tin model</h2>
          <dl className="divide-y divide-border">
            <Row label="Framework">{model.framework}</Row>
            <Row label="Kích thước đầu vào">
              <span className="tabular-nums">{model.input_size}</span>
            </Row>
            <Row label="Gradient">{model.supports_gradients ? 'Có' : 'Không'}</Row>
            <Row label={`Class (${model.class_names.length})`}>{model.class_names.join(', ')}</Row>
            <Row label="Hash weights">
              <TruncatedId value={model.weights_sha256} />
            </Row>
            <Row label="Đăng ký lúc">{formatDateTime(model.created_at)}</Row>
          </dl>
        </section>
      </div>
    </>
  )
}

/** `/admin/models/:id`: trạng thái, `ModelCheckResult`, "Kiểm tra lại" khi `check_failed`. */
export function ModelDetailPage() {
  const { id = '' } = useParams()
  const model = useModel(id)
  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-5 p-4 md:p-8">
      {model.isPending ? (
        <PageLoading />
      ) : model.isError ? (
        model.error instanceof ApiError && model.error.status === 404 ? (
          <EmptyState icon={SearchX} title="Không tìm thấy model">
            Model này không tồn tại. Quay lại danh sách model để chọn model khác.
          </EmptyState>
        ) : (
          <LoadError onRetry={() => void model.refetch()} retrying={model.isFetching} />
        )
      ) : (
        <ModelDetail model={model.data} />
      )}
    </div>
  )
}
