import { type FormEvent, type ReactNode, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router'

import { ApiError } from '@/api/errors'
import { errorMessage } from '@/api/messages'
import {
  adapterOf,
  buildCreate,
  EMPTY_FORM,
  enumValue,
  formFieldOf,
  type FormErrors,
  nextVersion,
  type ParamField,
  prefillFrom,
  type Realism,
  schemaFields,
  type SpecFormValues,
} from '@/admin/spec-form'
import { useAllAdminSpecs, useAttackAdapters, useCreateSpec } from '@/admin/useSpecAdmin'
import { FormAlert } from '@/components/FormAlert'
import { SelectField, TextareaField, TextField } from '@/components/form/TextField'
import { LoadError } from '@/components/LoadError'
import { PageLoading } from '@/components/PageLoading'
import { Button } from '@/components/ui/button'
import type { AttackAdapterInfo, AttackSpecAdminView } from '@/contracts/api'
import { CATALOG_COPY, REALISM_LABEL } from '@/copy/catalog'
import { ATTACK_KIND_LABEL } from '@/lib/attack-kinds'
import { PageHeader } from '@/layout/PageHeader'

/** Nhãn của spec trong ô "Sao chép từ": tên kỹ thuật đứng đầu để tìm nhanh. */
function sourceLabel(spec: AttackSpecAdminView): string {
  const display = spec.metadata?.display_name
  return `${spec.name} v${spec.version}${display ? ` · ${display}` : ''}`
}

function fieldsFor(adapter: AttackAdapterInfo | undefined): ParamField[] | null {
  if (!adapter) return []
  const result = schemaFields(adapter.params_schema)
  return result.supported ? result.fields : null
}

function ParamInput({
  field,
  value,
  error,
  onChange,
}: {
  field: ParamField
  value: string | undefined
  error?: string
  onChange: (value: string) => void
}) {
  const label = field.required ? field.key : `${field.key} (tùy chọn)`
  if (field.kind === 'enum') {
    return (
      <SelectField
        label={label}
        error={error}
        value={enumValue(value)}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">{field.required ? 'Chọn giá trị' : 'Không đặt'}</option>
        {field.options.map((option) => (
          <option key={JSON.stringify(option)} value={JSON.stringify(option)}>
            {String(option)}
          </option>
        ))}
      </SelectField>
    )
  }
  if (field.kind === 'boolean') {
    return (
      <label className="flex min-h-11 items-center gap-3 self-end">
        <input
          type="checkbox"
          role="switch"
          className="size-5"
          checked={value === 'true'}
          aria-checked={value === 'true'}
          onChange={(e) => onChange(e.target.checked ? 'true' : 'false')}
        />
        <span className="text-base">{field.key}</span>
      </label>
    )
  }
  const bounds = [
    field.min !== undefined ? `${field.exclusiveMin ? '>' : '≥'} ${field.min}` : null,
    field.max !== undefined ? `${field.exclusiveMax ? '<' : '≤'} ${field.max}` : null,
  ].filter(Boolean)
  return (
    <TextField
      label={label}
      type="number"
      inputMode="decimal"
      min={field.min}
      max={field.max}
      step={field.integer ? 1 : 'any'}
      hint={
        bounds.length ? `${field.integer ? 'Số nguyên' : 'Số'} ${bounds.join(', ')}` : undefined
      }
      error={error}
      value={value ?? ''}
      onChange={(e) => onChange(e.target.value)}
    />
  )
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="panel flex flex-col gap-4 p-5 md:p-6" aria-label={title}>
      <h2 className="text-base font-semibold">{title}</h2>
      {children}
    </section>
  )
}

function SpecForm({
  catalog,
  adapters,
  initial,
  newVersion,
}: {
  catalog: AttackSpecAdminView[]
  adapters: AttackAdapterInfo[]
  initial: SpecFormValues
  newVersion: boolean
}) {
  const navigate = useNavigate()
  const create = useCreateSpec()
  const [values, setValues] = useState(initial)
  const [errors, setErrors] = useState<FormErrors>({})
  const [formError, setFormError] = useState<string | null>(null)
  const sources = useMemo(
    () => [...catalog].sort((a, b) => a.name.localeCompare(b.name) || b.version - a.version),
    [catalog],
  )
  const adapter = adapters.find((a) => a.name === values.adapter)
  const fields = fieldsFor(adapter)
  const source = catalog.find((s) => s.id === values.sourceId)

  const set = <K extends keyof SpecFormValues>(key: K, value: SpecFormValues[K]) =>
    setValues((v) => ({ ...v, [key]: value }))

  function chooseSource(id: string) {
    const spec = catalog.find((s) => s.id === id)
    if (!spec) {
      set('sourceId', '')
      return
    }
    const sourceFields = fieldsFor(adapters.find((a) => a.name === adapterOf(spec))) ?? []
    // Tạo version mới giữ tên đã khóa; sao chép thì lấy mọi trường của nguồn.
    setValues({ ...prefillFrom(spec, sourceFields), name: newVersion ? values.name : spec.name })
    setErrors({})
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    setFormError(null)
    const result = buildCreate(values, { adapter, fields: fields ?? [], source, catalog })
    if (!result.ok) {
      setErrors(result.errors)
      return
    }
    setErrors({})
    create.mutate(
      { body: result.body, metadata: result.metadata },
      {
        onSuccess: (spec) => void navigate(`/admin/attacks/${spec.id}`),
        onError: (error) => {
          if (error instanceof ApiError && error.status === 409) {
            setErrors({ name: errorMessage(error) })
            return
          }
          const byField: FormErrors = {}
          if (error instanceof ApiError) {
            for (const f of error.fields) {
              const key = formFieldOf(f.path)
              if (key) byField[key] = f.message
            }
          }
          setErrors(byField)
          if (Object.keys(byField).length === 0) setFormError(errorMessage(error))
        },
      },
    )
  }

  const version = values.name.trim() ? nextVersion(values.name.trim(), catalog) : 1
  return (
    <form className="flex flex-col gap-5" onSubmit={submit} noValidate>
      <Section title="Nguồn và adapter">
        <div className="grid gap-4 md:grid-cols-2">
          <SelectField
            label="Sao chép từ"
            hint="Điền sẵn mọi trường từ một spec có sẵn."
            error={errors.sourceId}
            value={values.sourceId}
            onChange={(e) => chooseSource(e.target.value)}
          >
            <option value="">Không sao chép</option>
            {sources.map((spec) => (
              <option key={spec.id} value={spec.id}>
                {sourceLabel(spec)}
              </option>
            ))}
          </SelectField>
          <SelectField
            label="Adapter"
            error={errors.adapter}
            value={values.adapter}
            onChange={(e) => {
              set('adapter', e.target.value)
              set('params', {})
            }}
          >
            <option value="">Chọn adapter</option>
            {adapters.map((a) => (
              <option key={a.name} value={a.name}>
                {a.name} ({ATTACK_KIND_LABEL[a.kind]})
              </option>
            ))}
          </SelectField>
          <TextField
            label="Tên spec"
            readOnly={newVersion}
            autoComplete="off"
            hint={`Chữ thường, số, dấu gạch dưới. Spec sẽ có version ${version}.`}
            error={errors.name}
            value={values.name}
            onChange={(e) => set('name', e.target.value)}
          />
        </div>
      </Section>

      <Section title="Tham số cố định">
        {fields === null ? (
          <FormAlert>{CATALOG_COPY.unsupportedAdapter}</FormAlert>
        ) : fields.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            {adapter ? 'Adapter này không có tham số cố định.' : 'Chọn adapter để thấy tham số.'}
          </p>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {fields.map((field) => (
              <ParamInput
                key={field.key}
                field={field}
                value={values.params[field.key]}
                error={errors[`params.${field.key}`]}
                onChange={(v) => set('params', { ...values.params, [field.key]: v })}
              />
            ))}
          </div>
        )}
      </Section>

      <Section title="Dải level">
        <div className="grid gap-4 md:grid-cols-3">
          <TextField
            label="Tham số chính"
            hint="Ví dụ severity, eps."
            error={errors.primaryName}
            value={values.primaryName}
            onChange={(e) => set('primaryName', e.target.value)}
          />
          <SelectField
            label="Kiểu level"
            value={values.primaryType}
            onChange={(e) => set('primaryType', e.target.value as SpecFormValues['primaryType'])}
          >
            <option value="continuous">Liên tục</option>
            <option value="discrete">Rời rạc</option>
          </SelectField>
          <TextField
            label="Đơn vị"
            hint="Ví dụ severity, 1/255."
            error={errors.primaryUnit}
            value={values.primaryUnit}
            onChange={(e) => set('primaryUnit', e.target.value)}
          />
          <TextField
            label="Level nhỏ nhất"
            type="number"
            inputMode="decimal"
            step="any"
            error={errors.primaryMin}
            value={values.primaryMin}
            onChange={(e) => set('primaryMin', e.target.value)}
          />
          <TextField
            label="Level lớn nhất"
            type="number"
            inputMode="decimal"
            step="any"
            error={errors.primaryMax}
            value={values.primaryMax}
            onChange={(e) => set('primaryMax', e.target.value)}
          />
          {values.primaryType === 'discrete' && (
            <TextField
              label="Các level"
              hint="Ngăn bởi dấu phẩy, ví dụ 1, 2, 3."
              error={errors.primaryValues}
              value={values.primaryValues}
              onChange={(e) => set('primaryValues', e.target.value)}
            />
          )}
        </div>
      </Section>

      <Section title="Thông tin hiển thị">
        <p className="-mt-2 text-sm text-muted-foreground">
          Phần này không thuộc hash của spec; sửa được sau khi tạo.
        </p>
        <div className="grid gap-4 md:grid-cols-2">
          <TextField
            label="Tên hiển thị"
            error={errors.displayName}
            value={values.displayName}
            onChange={(e) => set('displayName', e.target.value)}
          />
          <SelectField
            label="Mức sát thực tế"
            error={errors.realism}
            value={values.realism}
            onChange={(e) => set('realism', e.target.value as Realism)}
          >
            {(Object.keys(REALISM_LABEL) as Realism[]).map((r) => (
              <option key={r} value={r}>
                {REALISM_LABEL[r]}
              </option>
            ))}
          </SelectField>
          <TextareaField
            label="Mô tả"
            error={errors.description}
            value={values.description}
            onChange={(e) => set('description', e.target.value)}
          />
          <TextareaField
            label="Nhãn level"
            hint='Mỗi dòng "level: nhãn", ví dụ "1: lất phất". Để trống nếu không cần.'
            error={errors.levelLabels}
            value={values.levelLabels}
            onChange={(e) => set('levelLabels', e.target.value)}
          />
        </div>
      </Section>

      {formError && <FormAlert>{formError}</FormAlert>}
      <div className="flex flex-col-reverse gap-2 md:flex-row md:justify-end">
        <Button type="button" variant="outline" onClick={() => void navigate('/admin/attacks')}>
          Hủy
        </Button>
        <Button type="submit" size="lg" disabled={fields === null || create.isPending}>
          {create.isPending ? 'Đang tạo…' : 'Tạo spec'}
        </Button>
      </div>
    </form>
  )
}

/**
 * `/admin/attacks/new` (requirements.md Phase R3, mục Admin catalog và model): `?from=<id>` điền
 * sẵn từ spec có sẵn; thêm `&mode=version` để tạo version mới cùng tên.
 */
export function SpecCreatePage() {
  const [params] = useSearchParams()
  const catalog = useAllAdminSpecs()
  const adapters = useAttackAdapters()
  const newVersion = params.get('mode') === 'version'
  const from = params.get('from')

  let body: ReactNode
  if (catalog.isPending || adapters.isPending) body = <PageLoading />
  else if (catalog.isError || adapters.isError) {
    body = (
      <LoadError
        onRetry={() => {
          void catalog.refetch()
          void adapters.refetch()
        }}
        retrying={catalog.isFetching || adapters.isFetching}
      />
    )
  } else {
    const source = catalog.data.find((s) => s.id === from)
    const sourceAdapter = source && adapters.data.find((a) => a.name === adapterOf(source))
    const initial = source ? prefillFrom(source, fieldsFor(sourceAdapter) ?? []) : EMPTY_FORM
    body = (
      <SpecForm
        catalog={catalog.data}
        adapters={adapters.data}
        initial={initial}
        newVersion={newVersion && source !== undefined}
      />
    )
  }
  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-5 p-4 md:p-8">
      <PageHeader
        back={{ to: '/admin/attacks', label: 'Attack catalog' }}
        title={newVersion ? 'Tạo version mới' : 'Tạo attack spec'}
        description="Spec mới được worker tự kiểm tra 7 mục. Đạt thì chờ một reviewer kích hoạt; sau đó spec mới có trong wizard."
      />
      {body}
    </div>
  )
}
