import {
  Archive,
  ArchiveRestore,
  CircleCheck,
  CircleX,
  Plus,
  RotateCw,
  SearchX,
  Trash2,
} from 'lucide-react'
import { type ReactNode, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router'

import { ApiError } from '@/api/errors'
import { errorMessage } from '@/api/messages'
import { formatDateTime } from '@/admin/format'
import { mappedCount } from '@/admin/class-mapping'
import { canManageModel } from '@/admin/model-owner'
import { ClassMappingFields } from '@/admin/ClassMappingFields'
import { useMappingDraft } from '@/admin/mapping-draft'
import {
  useArchiveModel,
  useCreateMapping,
  useDeleteModel,
  useModel,
  useModelMappings,
  useRecheckModel,
} from '@/admin/useModelAdmin'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { TruncatedId } from '@/components/CopyButton'
import { EmptyState } from '@/components/EmptyState'
import { FormAlert } from '@/components/FormAlert'
import { LoadError } from '@/components/LoadError'
import { PageLoading } from '@/components/PageLoading'
import { StatusBadge } from '@/components/status/StatusBadge'
import { Button } from '@/components/ui/button'
import type { ClassMappingSummary, DatasetSummary, ModelSummary } from '@/contracts/api'
import { CATALOG_COPY } from '@/copy/catalog'
import { MODEL_ADMIN_COPY } from '@/copy/model-admin'
import { useDatasets } from '@/features/wizard/api'
import { useMe } from '@/auth/useMe'
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

function datasetName(datasets: readonly DatasetSummary[], versionId: string): string {
  const dataset = datasets.find((d) => d.versions.some((v) => v.id === versionId))
  return dataset?.name ?? 'Dataset'
}

function MappingItem({
  mapping,
  datasets,
}: {
  mapping: ClassMappingSummary
  datasets: readonly DatasetSummary[]
}) {
  const pairs = Object.entries(mapping.classes)
  return (
    <li className="flex flex-col gap-1 py-3">
      <p className="text-sm font-medium">
        {datasetName(datasets, mapping.dataset_version_id)} ·{' '}
        {mapping.preset ? `preset ${mapping.preset}` : 'tự chọn'} · {mappedCount(mapping.classes)}/
        {pairs.length} class được tính
      </p>
      <p className="text-sm break-words text-muted-foreground">
        {pairs.map(([source, target]) => `${source} → ${target ?? 'bỏ qua'}`).join(', ')}
      </p>
    </li>
  )
}

/** Class mapping của model (đề xuất contract 002): danh sách và form thêm mapping mới. */
function MappingSection({
  model,
  canManage,
  initialError,
}: {
  model: ModelSummary
  canManage: boolean
  initialError?: string
}) {
  const copy = MODEL_ADMIN_COPY
  const mappings = useModelMappings(model.id)
  const datasets = useDatasets()
  const create = useCreateMapping()
  const draft = useMappingDraft(datasets.data ?? [], model.class_names)
  const [adding, setAdding] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const archived = model.archived_at != null
  const list = mappings.data ?? []

  function save() {
    setSubmitted(true)
    const body = draft.body(model.id)
    if (!body) return
    create.mutate(body, {
      onSuccess: () => {
        setAdding(false)
        setSubmitted(false)
      },
    })
  }

  return (
    <section
      className="panel flex flex-col gap-3 p-5"
      aria-label={copy.mappingTitle}
      data-testid="model-mappings"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-base font-semibold">{copy.mappingTitle}</h2>
        {!adding && !archived && canManage && (
          <Button variant="outline" onClick={() => setAdding(true)}>
            <Plus aria-hidden />
            {copy.addMapping}
          </Button>
        )}
      </div>
      {initialError && !create.isSuccess && <FormAlert>{initialError}</FormAlert>}
      {mappings.isPending ? (
        <PageLoading />
      ) : mappings.isError ? (
        <LoadError onRetry={() => void mappings.refetch()} retrying={mappings.isFetching} />
      ) : list.length === 0 ? (
        <p className="text-sm text-muted-foreground">{copy.noMapping}</p>
      ) : (
        <ul className="divide-y divide-border">
          {list.map((mapping) => (
            <MappingItem key={mapping.id} mapping={mapping} datasets={datasets.data ?? []} />
          ))}
        </ul>
      )}
      {adding && (
        <div className="flex flex-col gap-3 border-t border-border pt-3">
          <ClassMappingFields
            draft={draft}
            modelClasses={model.class_names}
            showError={submitted}
          />
          {create.isError && <FormAlert>{errorMessage(create.error)}</FormAlert>}
          <div className="flex flex-col-reverse gap-2 md:flex-row md:justify-end">
            <Button variant="outline" onClick={() => setAdding(false)} disabled={create.isPending}>
              Hủy
            </Button>
            <Button onClick={save} disabled={create.isPending || draft.options.length === 0}>
              {create.isPending ? 'Đang lưu…' : copy.saveMapping}
            </Button>
          </div>
        </div>
      )}
    </section>
  )
}

function ModelActions({ model }: { model: ModelSummary }) {
  const copy = MODEL_ADMIN_COPY
  const navigate = useNavigate()
  const recheck = useRecheckModel()
  const archive = useArchiveModel()
  const remove = useDeleteModel()
  const [dialog, setDialog] = useState<'archive' | 'delete' | null>(null)
  const archived = model.archived_at != null
  return (
    <>
      <div className="flex flex-wrap gap-2">
        {model.status === 'check_failed' && (
          <Button disabled={recheck.isPending} onClick={() => recheck.mutate(model.id)}>
            <RotateCw aria-hidden />
            Kiểm tra lại
          </Button>
        )}
        {archived ? (
          <Button
            variant="outline"
            disabled={archive.isPending}
            onClick={() => archive.mutate({ id: model.id, archived: false })}
          >
            <ArchiveRestore aria-hidden />
            {copy.restore}
          </Button>
        ) : (
          <Button variant="outline" onClick={() => setDialog('archive')}>
            <Archive aria-hidden />
            {copy.archive}
          </Button>
        )}
        <Button
          variant="outline"
          className="text-fail"
          disabled={model.status === 'checking'}
          onClick={() => setDialog('delete')}
        >
          <Trash2 aria-hidden />
          {copy.delete}
        </Button>
      </div>
      <ConfirmDialog
        open={dialog === 'archive'}
        onOpenChange={(open) => setDialog(open ? 'archive' : null)}
        title={copy.archiveTitle}
        description={copy.archiveConsequence}
        confirmLabel={copy.archive}
        pending={archive.isPending}
        onConfirm={() =>
          archive.mutate({ id: model.id, archived: true }, { onSuccess: () => setDialog(null) })
        }
      />
      <ConfirmDialog
        open={dialog === 'delete'}
        onOpenChange={(open) => setDialog(open ? 'delete' : null)}
        title={copy.deleteTitle}
        description={copy.deleteConsequence}
        confirmLabel={copy.delete}
        destructive
        pending={remove.isPending}
        onConfirm={() =>
          remove.mutate(model.id, {
            onSuccess: () => void navigate('/models'),
            onError: () => setDialog(null),
          })
        }
      />
      {[recheck, archive, remove].map((mutation, i) =>
        mutation.isError ? <FormAlert key={i}>{errorMessage(mutation.error)}</FormAlert> : null,
      )}
    </>
  )
}

function ModelDetail({ model }: { model: ModelSummary }) {
  const location = useLocation()
  const state = location.state as { mappingError?: string } | null
  const archived = model.archived_at != null
  const canManage = canManageModel(model, useMe().data)
  return (
    <>
      <PageHeader
        back={{ to: '/models', label: 'Model' }}
        eyebrow={model.framework}
        title={model.name}
      />
      <div className="flex flex-wrap items-center gap-3">
        <span data-testid="model-status">
          <StatusBadge kind="model" status={archived ? 'archived' : model.status} />
        </span>
        {model.status === 'checking' && (
          <span className="text-sm text-muted-foreground">{CATALOG_COPY.checkingNote}</span>
        )}
        {archived && (
          <span className="text-sm text-muted-foreground">{MODEL_ADMIN_COPY.archivedNote}</span>
        )}
      </div>
      {canManage ? (
        <ModelActions model={model} />
      ) : (
        <p className="text-sm text-muted-foreground" data-testid="model-owner-note">
          {MODEL_ADMIN_COPY.notOwner(model.owner_name)}
        </p>
      )}
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
      <MappingSection
        model={model}
        canManage={canManage}
        initialError={
          state?.mappingError
            ? MODEL_ADMIN_COPY.mappingFailedAfterRegister(state.mappingError)
            : undefined
        }
      />
    </>
  )
}

/** `/models/:id`: trạng thái, `ModelCheckResult`, "Kiểm tra lại" khi `check_failed`. */
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
