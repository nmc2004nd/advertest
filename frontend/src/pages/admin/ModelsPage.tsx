import { Boxes, FileCheck2, Plus } from 'lucide-react'
import { type FormEvent, useCallback, useState } from 'react'
import { Link, useNavigate } from 'react-router'

import { ApiError } from '@/api/errors'
import { errorMessage } from '@/api/messages'
import { formatDateTime } from '@/admin/format'
import {
  CLASS_PRESETS,
  type ClassPreset,
  DEFAULT_INPUT_SIZE,
  frameworkFromFile,
  INPUT_SIZES,
  nameFromFile,
  ONNX_ARCHITECTURES,
  readWeightsMeta,
  type WeightsMeta,
} from '@/admin/model-defaults'
import {
  needsConversion,
  parseClassNames,
  TORCHVISION_ARCHITECTURES,
  ULTRALYTICS_ARCHITECTURES,
  ULTRALYTICS_INPUT_SIZE,
  weightsFileError,
} from '@/admin/model-file'
import { ClassMappingFields } from '@/admin/ClassMappingFields'
import { useMappingDraft } from '@/admin/mapping-draft'
import { useCreateMapping, useModelList, useRegisterModel } from '@/admin/useModelAdmin'
import { EmptyState } from '@/components/EmptyState'
import { FormAlert } from '@/components/FormAlert'
import { SelectField, TextareaField, TextField } from '@/components/form/TextField'
import { LoadError } from '@/components/LoadError'
import { PageLoading } from '@/components/PageLoading'
import { StatusBadge } from '@/components/status/StatusBadge'
import { Button } from '@/components/ui/button'
import type { ModelConversionView, ModelSummary } from '@/contracts/api'
import { CATALOG_COPY } from '@/copy/catalog'
import { MODEL_ADMIN_COPY } from '@/copy/model-admin'
import { useDatasets } from '@/features/wizard/api'
import { PageHero } from '@/layout/PageHero'
import { cn } from '@/lib/utils'

import { ConvertPanel } from './ConvertPanel'

type Framework = 'torchvision' | 'onnx' | 'ultralytics'

/** Cách đổi `.pt` của Ultralytics sang safetensors (có gradient). */
export function UltralyticsHint() {
  const copy = CATALOG_COPY.ultralyticsHint
  return (
    <div
      data-testid="ultralytics-hint"
      className="rounded-lg border border-border bg-surface-raised p-3 text-sm"
    >
      <p className="font-semibold">{copy.intro}</p>
      <code className="mt-1 block overflow-x-auto font-mono text-[13px]">{copy.command}</code>
      <p className="mt-1 text-muted-foreground">{copy.outro}</p>
    </div>
  )
}

export function OnnxLayouts() {
  const copy = CATALOG_COPY.onnxLayouts
  return (
    <div
      data-testid="onnx-layouts"
      className="rounded-lg border border-border bg-surface-raised p-3 text-sm"
    >
      <p className="font-semibold">{copy.intro}</p>
      <ul className="mt-1 list-disc pl-5">
        <li>{copy.yolo}</li>
        <li>{copy.nms}</li>
      </ul>
      <p className="mt-1 text-muted-foreground">{copy.outro}</p>
    </div>
  )
}

function failureText(error: unknown): string {
  return error instanceof Error && !(error instanceof ApiError)
    ? error.message
    : errorMessage(error)
}

const CHIP =
  'inline-flex min-h-11 min-w-11 items-center justify-center rounded-full border px-3.5 text-sm tabular-nums transition-colors duration-150 focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none'
const OTHER = '__khac__'

/** Bộ class mặc định khi file không có metadata: torchvision COCO 91, YOLO (ONNX, Ultralytics)
 * COCO 80. */
const defaultPreset = (framework: Framework): ClassPreset =>
  framework === 'torchvision' ? 'coco91' : 'coco80'

export function RegisterModelForm({ onCancel }: { onCancel: () => void }) {
  const navigate = useNavigate()
  const [progress, setProgress] = useState<number | null>(null)
  const register = useRegisterModel(setProgress)
  const [name, setName] = useState('')
  const [nameTouched, setNameTouched] = useState(false)
  const [framework, setFramework] = useState<Framework>('torchvision')
  const [architecture, setArchitecture] = useState<string>(TORCHVISION_ARCHITECTURES[0])
  const [otherArchitecture, setOtherArchitecture] = useState(false)
  const [classPreset, setClassPreset] = useState<ClassPreset>(defaultPreset('torchvision'))
  const [customClasses, setCustomClasses] = useState('')
  const [inputSize, setInputSize] = useState(String(DEFAULT_INPUT_SIZE))
  const [file, setFile] = useState<File | null>(null)
  const [meta, setMeta] = useState<WeightsMeta>({})
  const [submitted, setSubmitted] = useState(false)
  const datasets = useDatasets()
  const createMapping = useCreateMapping()
  const [withMapping, setWithMapping] = useState(true)
  // Kết quả chuyển `.pt` trong sandbox (đề xuất contract 003): đăng ký bằng upload_id này.
  const [convertedUploadId, setConvertedUploadId] = useState<string | null>(null)

  const fileError = file ? weightsFileError(file) : null
  const presetNames =
    classPreset === 'file'
      ? (meta.classNames ?? [])
      : classPreset === 'custom'
        ? null
        : CLASS_PRESETS[classPreset].names
  const classNames = presetNames ?? parseClassNames(customClasses)
  const modelClasses = classNames instanceof Error ? [] : classNames
  const mapping = useMappingDraft(datasets.data ?? [], modelClasses)
  const mappingOn = withMapping && mapping.options.length > 0
  const size = Number(inputSize)
  const sizes =
    framework === 'ultralytics'
      ? [ULTRALYTICS_INPUT_SIZE]
      : [...new Set([...INPUT_SIZES, ...(meta.inputSize ? [meta.inputSize] : [])])].sort(
          (a, b) => a - b,
        )
  const errors = {
    name: name.trim() === '' ? 'Bắt buộc.' : undefined,
    architecture: architecture.trim() === '' ? 'Bắt buộc.' : undefined,
    classes: classNames instanceof Error ? classNames.message : undefined,
    inputSize: Number.isInteger(size) && size > 0 ? undefined : 'Nhập số nguyên dương, ví dụ 640.',
    file: !file
      ? 'Chọn file weights.'
      : needsConversion(file.name) && !convertedUploadId
        ? MODEL_ADMIN_COPY.convertFirst
        : convertedUploadId && framework === 'onnx'
          ? MODEL_ADMIN_COPY.convertedNotOnnx
          : undefined,
    mapping: mappingOn ? (mapping.error ?? undefined) : undefined,
  }
  const invalid = Object.values(errors).some(Boolean)

  function chooseFramework(value: Framework, detected: WeightsMeta = meta) {
    setFramework(value)
    const allowed: readonly string[] =
      value === 'torchvision'
        ? TORCHVISION_ARCHITECTURES
        : value === 'ultralytics'
          ? ULTRALYTICS_ARCHITECTURES
          : ONNX_ARCHITECTURES
    setArchitecture(allowed.find((a) => a === detected.architecture) ?? allowed[0])
    setOtherArchitecture(false)
    if (value === 'ultralytics') setInputSize(String(ULTRALYTICS_INPUT_SIZE))
    if (!detected.classNames) setClassPreset(defaultPreset(value))
  }

  async function chooseFile(next: File | null) {
    setFile(next)
    setMeta({})
    setConvertedUploadId(null)
    if (!next || weightsFileError(next)) return
    if (!nameTouched) setName(nameFromFile(next.name))
    if (needsConversion(next.name)) return // metadata có sau khi sandbox chuyển xong
    const detected = await readWeightsMeta(next)
    setMeta(detected)
    const detectedFramework = frameworkFromFile(next.name, detected)
    if (detectedFramework) chooseFramework(detectedFramework, detected)
    if (detected.classNames?.length) setClassPreset('file')
    if (detected.inputSize && detectedFramework !== 'ultralytics') {
      setInputSize(String(detected.inputSize))
    }
  }

  const onConverted = useCallback(
    (view: ModelConversionView) => {
      const m = view.metadata
      if (!m || !view.result_upload_id) return
      const detected: WeightsMeta = {
        framework: m.framework,
        architecture: m.architecture ?? undefined,
        classNames: m.class_names ?? undefined,
        inputSize: m.input_size ?? undefined,
      }
      setMeta(detected)
      chooseFramework(m.framework, detected)
      if (detected.classNames?.length) setClassPreset('file')
      if (detected.inputSize && m.framework !== 'ultralytics') {
        setInputSize(String(detected.inputSize))
      }
      setConvertedUploadId(view.result_upload_id)
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps -- chooseFramework chỉ đặt state
    [],
  )

  function submit(event: FormEvent) {
    event.preventDefault()
    setSubmitted(true)
    if (invalid || fileError || !file || classNames instanceof Error) return
    register.mutate(
      {
        name: name.trim(),
        framework,
        architecture: architecture.trim(),
        class_names: classNames,
        input_size: size,
        ...(convertedUploadId ? { upload_id: convertedUploadId } : { file }),
      },
      {
        onSuccess: (model) => {
          const body = mappingOn ? mapping.body(model.id) : null
          if (!body) {
            void navigate(`/models/${model.id}`)
            return
          }
          // Mapping lỗi thì model vẫn đã đăng ký: sang trang model, báo lỗi để thêm lại ở đó.
          createMapping.mutate(body, {
            onSettled: (_, error) =>
              void navigate(`/models/${model.id}`, {
                state: error ? { mappingError: failureText(error) } : null,
              }),
          })
        },
      },
    )
  }

  const shown = (message: string | undefined) => (submitted ? message : undefined)
  const detectedText = [
    meta.architecture && `kiến trúc ${meta.architecture}`,
    meta.classNames && `${meta.classNames.length} class`,
    meta.inputSize && `kích thước ${meta.inputSize}`,
  ].filter(Boolean)
  return (
    <form
      className="panel flex flex-col gap-4 p-5 md:p-6"
      aria-label="Đăng ký model"
      onSubmit={submit}
      noValidate
    >
      <h2 className="text-base font-semibold">Đăng ký model</h2>
      <div className="flex flex-col gap-2">
        <TextField
          label="File weights"
          type="file"
          accept=".onnx,.safetensors,.pt,.pth"
          className="py-2"
          hint="Chọn file trước: framework, tên, kiến trúc, class và kích thước được điền sẵn từ file. Nhận .onnx, .safetensors, hoặc .pt/.pth (chuyển sang .safetensors trong sandbox); tối đa 500 MB."
          error={fileError ?? shown(errors.file)}
          onChange={(e) => void chooseFile(e.target.files?.[0] ?? null)}
        />
        {file && !fileError && needsConversion(file.name) && (
          <ConvertPanel
            key={`${file.name}:${file.size}:${file.lastModified}`}
            file={file}
            onDone={onConverted}
          />
        )}
        {detectedText.length > 0 && (
          <p data-testid="weights-meta" className="flex items-center gap-2 text-sm text-approved">
            <FileCheck2 aria-hidden="true" className="size-4 shrink-0" />
            Đọc được từ file: {detectedText.join(', ')}.
          </p>
        )}
        {progress !== null && register.isPending && (
          <div className="flex flex-col gap-1">
            <div
              role="progressbar"
              aria-label="Tiến độ tải lên"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round(progress * 100)}
              className="h-2 overflow-hidden rounded-full bg-surface-raised"
            >
              <div
                className="h-full bg-detect transition-[width] duration-200 ease-out"
                style={{ width: `${Math.round(progress * 100)}%` }}
              />
            </div>
            <span className="text-xs text-muted-foreground tabular-nums">
              {progress < 1 ? `Đang tải lên ${Math.round(progress * 100)}%` : 'Đang đăng ký…'}
            </span>
          </div>
        )}
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <TextField
          label="Tên model"
          autoComplete="off"
          hint="Mặc định lấy theo tên file; sửa nếu muốn."
          error={shown(errors.name)}
          value={name}
          onChange={(e) => {
            setName(e.target.value)
            setNameTouched(true)
          }}
        />
        <SelectField
          label="Framework"
          value={framework}
          onChange={(e) => chooseFramework(e.target.value as Framework)}
        >
          <option value="ultralytics">ultralytics YOLO (.safetensors, có gradient)</option>
          <option value="torchvision">torchvision (.safetensors, có gradient)</option>
          <option value="onnx">onnx (.onnx, không có gradient)</option>
        </SelectField>
        {framework !== 'onnx' ? (
          <SelectField
            label="Kiến trúc"
            value={architecture}
            onChange={(e) => setArchitecture(e.target.value)}
          >
            {(framework === 'torchvision'
              ? TORCHVISION_ARCHITECTURES
              : ULTRALYTICS_ARCHITECTURES
            ).map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </SelectField>
        ) : (
          <div className="flex flex-col gap-2">
            <SelectField
              label="Kiến trúc"
              value={otherArchitecture ? OTHER : architecture}
              onChange={(e) => {
                const other = e.target.value === OTHER
                setOtherArchitecture(other)
                setArchitecture(other ? '' : e.target.value)
              }}
            >
              {ONNX_ARCHITECTURES.map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
              <option value={OTHER}>Khác (tự mô tả)…</option>
            </SelectField>
            {otherArchitecture && (
              <TextField
                label="Mô tả kiến trúc"
                hint="Ví dụ: DETR ResNet-50 xuất ONNX opset 17."
                error={shown(errors.architecture)}
                value={architecture}
                onChange={(e) => setArchitecture(e.target.value)}
              />
            )}
          </div>
        )}
        <div className="flex flex-col gap-1.5">
          <p id="kich-thuoc" className="text-[14px] font-semibold">
            Kích thước đầu vào
          </p>
          <div role="radiogroup" aria-labelledby="kich-thuoc" className="flex flex-wrap gap-2">
            {sizes.map((v) => {
              const on = size === v
              return (
                <button
                  key={v}
                  type="button"
                  role="radio"
                  aria-checked={on}
                  onClick={() => setInputSize(String(v))}
                  className={cn(
                    CHIP,
                    on
                      ? 'border-navy bg-navy text-primary-foreground'
                      : 'border-line bg-surface-solid hover:border-input',
                  )}
                >
                  {v}
                </button>
              )
            })}
          </div>
          <p className="text-[13px] leading-5 text-muted-foreground">
            Cạnh ảnh vuông sau letterbox, mặc định 640.
          </p>
        </div>
      </div>
      <div className="flex flex-col gap-2">
        <SelectField
          label="Danh sách class"
          hint="Theo thứ tự index của model; số class phải khớp đầu ra của weights."
          error={shown(errors.classes)}
          value={classPreset}
          onChange={(e) => setClassPreset(e.target.value as ClassPreset)}
        >
          {meta.classNames?.length ? (
            <option value="file">Đọc từ file weights ({meta.classNames.length} class)</option>
          ) : null}
          {(Object.keys(CLASS_PRESETS) as Exclude<ClassPreset, 'file'>[]).map((k) => (
            <option key={k} value={k}>
              {CLASS_PRESETS[k].label}
            </option>
          ))}
        </SelectField>
        {presetNames ? (
          <details className="rounded-lg border border-line px-3 py-1 text-sm">
            <summary className="flex min-h-11 cursor-pointer items-center">
              {presetNames.length} class: {presetNames.slice(0, 6).join(', ')}
              {presetNames.length > 6 ? ', …' : ''}
            </summary>
            <div className="flex flex-col gap-2 pb-3">
              <p className="max-h-40 overflow-y-auto text-muted-foreground">
                {presetNames.join(', ')}
              </p>
              <Button
                type="button"
                variant="outline"
                className="self-start"
                onClick={() => {
                  setCustomClasses(presetNames.join('\n'))
                  setClassPreset('custom')
                }}
              >
                Sửa danh sách này
              </Button>
            </div>
          </details>
        ) : (
          <TextareaField
            label="Class (mỗi dòng một class)"
            hint="Hoặc ngăn bởi dấu phẩy."
            error={shown(errors.classes)}
            value={customClasses}
            onChange={(e) => setCustomClasses(e.target.value)}
          />
        )}
      </div>
      <fieldset className="flex flex-col gap-3 rounded-lg border border-line p-4">
        <legend className="px-1 text-[14px] font-semibold">{MODEL_ADMIN_COPY.mappingTitle}</legend>
        <p className="text-[13px] leading-5 text-muted-foreground">
          {MODEL_ADMIN_COPY.mappingIntro}
        </p>
        <label className="flex min-h-11 items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={withMapping}
            onChange={(e) => setWithMapping(e.target.checked)}
            className="size-4 accent-[var(--cta)]"
          />
          {MODEL_ADMIN_COPY.createMappingNow}
        </label>
        {withMapping &&
          (datasets.isPending ? (
            <p className="text-sm text-muted-foreground">Đang tải danh sách dataset…</p>
          ) : (
            <ClassMappingFields draft={mapping} modelClasses={modelClasses} showError={submitted} />
          ))}
      </fieldset>
      {framework === 'onnx' && <OnnxLayouts />}
      {framework === 'ultralytics' && <UltralyticsHint />}
      {register.isError && <FormAlert>{failureText(register.error)}</FormAlert>}
      <div className="flex flex-col-reverse gap-2 md:flex-row md:justify-end">
        <Button
          type="button"
          variant="outline"
          onClick={onCancel}
          disabled={register.isPending || createMapping.isPending}
        >
          Hủy
        </Button>
        <Button
          type="submit"
          disabled={fileError !== null || register.isPending || createMapping.isPending}
        >
          {register.isPending || createMapping.isPending ? 'Đang đăng ký…' : 'Đăng ký'}
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        Sau khi đăng ký, worker kiểm tra model (nạp, so hash, chạy thử trên ảnh mẫu). Chỉ model Sẵn
        sàng mới dùng được trong experiment và thử nhanh.
      </p>
    </form>
  )
}

function ModelName({ model }: { model: ModelSummary }) {
  return (
    <Link
      to={`/models/${model.id}`}
      className="font-medium text-cta underline-offset-4 hover:underline focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
    >
      {model.name}
    </Link>
  )
}

const HEADERS = [
  'Tên',
  'Framework',
  'Class',
  'Đầu vào',
  'Gradient',
  'Người đăng ký',
  'Đăng ký lúc',
  'Trạng thái',
]

function ModelTable({ models }: { models: ModelSummary[] }) {
  return (
    <div className="hidden overflow-x-auto rounded-xl border border-border lg:block">
      <table className="w-full text-left text-sm">
        <caption className="sr-only">Model đã đăng ký</caption>
        <thead className="bg-muted/50">
          <tr>
            {HEADERS.map((h) => (
              <th key={h} scope="col" className="px-3 py-2 font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {models.map((m) => (
            <tr key={m.id} className="border-t border-border align-top">
              <td className="px-3 py-3">
                <ModelName model={m} />
              </td>
              <td className="px-3 py-3">{m.framework}</td>
              <td className="px-3 py-3 text-right tabular-nums">{m.class_names.length}</td>
              <td className="px-3 py-3 text-right tabular-nums">{m.input_size}</td>
              <td className="px-3 py-3">{m.supports_gradients ? 'Có' : 'Không'}</td>
              <td className="px-3 py-3">{m.owner_name ?? '—'}</td>
              <td className="px-3 py-3 tabular-nums">{formatDateTime(m.created_at)}</td>
              <td className="px-3 py-3">
                <StatusBadge kind="model" status={m.archived_at ? 'archived' : m.status} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ModelCards({ models }: { models: ModelSummary[] }) {
  return (
    <ul className="flex flex-col gap-3 lg:hidden">
      {models.map((m) => (
        <li key={m.id} className="panel flex flex-col gap-2 p-4">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <ModelName model={m} />
            <StatusBadge kind="model" status={m.archived_at ? 'archived' : m.status} />
          </div>
          <p className="text-sm text-muted-foreground tabular-nums">
            {m.framework} · {m.class_names.length} class · đầu vào {m.input_size} · gradient:{' '}
            {m.supports_gradients ? 'có' : 'không'}
            {m.owner_name ? ` · ${m.owner_name}` : ''}
          </p>
        </li>
      ))}
    </ul>
  )
}

/** `/models` (requirements.md Phase R3, mục Đăng ký model; permission `model.manage`). */
export function ModelsPage() {
  const models = useModelList()
  const [registering, setRegistering] = useState(false)
  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-5 p-4 md:p-8">
      <PageHero
        compact
        title="Model"
        description="Bạn thấy model mình đăng ký và model dùng chung do admin đăng ký. Model đăng ký qua web được worker kiểm tra trước khi dùng; file .pt/.pth được chuyển sang .safetensors trong sandbox trước."
        actions={
          registering ? undefined : (
            <Button size="lg" onClick={() => setRegistering(true)}>
              <Plus aria-hidden />
              Đăng ký model
            </Button>
          )
        }
      />
      {registering && <RegisterModelForm onCancel={() => setRegistering(false)} />}
      {models.isPending ? (
        <PageLoading />
      ) : models.isError ? (
        <LoadError onRetry={() => void models.refetch()} retrying={models.isFetching} />
      ) : models.data.length === 0 ? (
        <EmptyState icon={Boxes} title="Chưa có model nào">
          Đăng ký model đầu tiên để kỹ sư chọn được trong wizard.
        </EmptyState>
      ) : (
        <>
          <ModelTable models={models.data} />
          <ModelCards models={models.data} />
        </>
      )}
    </div>
  )
}
