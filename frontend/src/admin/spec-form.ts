// Form tạo attack spec (requirements.md Phase R3, mục Admin catalog và model): form tham số sinh từ
// `params_schema` của adapter, điền sẵn từ spec có sẵn, dựng body `POST /admin/attack-specs`.
import type {
  AttackAdapterInfo,
  AttackSpecAdminView,
  AttackSpecCreate,
  AttackSpecMetadata,
} from '@/contracts/api'

type JsonValue = AttackSpecAdminView['fixed_params'][string]
type Spec = Pick<AttackSpecAdminView, 'kind' | 'art_class' | 'adapter'>

/** Một tham số của `fixed_params` trên form. */
export type ParamField =
  | { key: string; required: boolean; kind: 'enum'; options: JsonValue[] }
  | {
      key: string
      required: boolean
      kind: 'number'
      integer: boolean
      /** Giới hạn đã gộp `minimum`/`exclusiveMinimum` (và tương tự cho max). */
      min?: number
      max?: number
      exclusiveMin: boolean
      exclusiveMax: boolean
    }
  | { key: string; required: boolean; kind: 'boolean' }

export type SchemaFields = { supported: true; fields: ParamField[] } | { supported: false }

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function numberOrUndefined(value: unknown): number | undefined {
  return typeof value === 'number' ? value : undefined
}

function fieldOf(key: string, schema: unknown, required: boolean): ParamField | null {
  if (!isRecord(schema)) return null
  if (Array.isArray(schema.enum) && schema.enum.length > 0) {
    return { key, required, kind: 'enum', options: schema.enum as JsonValue[] }
  }
  if (schema.type === 'boolean') return { key, required, kind: 'boolean' }
  if (schema.type === 'integer' || schema.type === 'number') {
    const exMin = numberOrUndefined(schema.exclusiveMinimum)
    const exMax = numberOrUndefined(schema.exclusiveMaximum)
    return {
      key,
      required,
      kind: 'number',
      integer: schema.type === 'integer',
      min: exMin ?? numberOrUndefined(schema.minimum),
      max: exMax ?? numberOrUndefined(schema.maximum),
      exclusiveMin: exMin !== undefined,
      exclusiveMax: exMax !== undefined,
    }
  }
  return null
}

/**
 * Trường của form theo `params_schema`: enum → danh sách chọn, số → ô số có giới hạn, boolean →
 * công tắc. Có kiểu khác (mảng, object lồng, chuỗi tự do) thì `supported = false`.
 */
export function schemaFields(schema: AttackAdapterInfo['params_schema']): SchemaFields {
  if (schema.type !== undefined && schema.type !== 'object') return { supported: false }
  const properties = schema.properties ?? {}
  if (!isRecord(properties)) return { supported: false }
  const required = new Set(Array.isArray(schema.required) ? (schema.required as string[]) : [])
  const fields: ParamField[] = []
  for (const [key, sub] of Object.entries(properties)) {
    const field = fieldOf(key, sub, required.has(key))
    if (!field) return { supported: false }
    fields.push(field)
  }
  return { supported: true, fields }
}

// ---------------------------------------------------------------- Adapter của spec

const PATCH_ART_CLASS = 'RobustDPatch'

/** Adapter của spec: `adapter`, hoặc suy từ `kind` và `art_class` (`attacks.builders.adapter_of`). */
export function adapterOf(spec: Spec): string {
  if (spec.adapter) return spec.adapter
  if (spec.kind === 'corruption') return 'corruption.imagecorruptions'
  if (spec.kind === 'occlusion') return 'occlusion.bbox'
  return spec.art_class === PATCH_ART_CLASS ? 'patch.robust_dpatch' : 'art.evasion'
}

/** Version tiếp theo của `name`: lớn nhất trong catalog + 1, tên mới là 1. */
export function nextVersion(name: string, catalog: readonly AttackSpecAdminView[]): number {
  return Math.max(0, ...catalog.filter((s) => s.name === name).map((s) => s.version)) + 1
}

// ---------------------------------------------------------------- Trạng thái form

export type Realism = AttackSpecMetadata['realism']

/** Giá trị đang nhập (chuỗi như trong ô nhập; chuyển kiểu khi dựng body). */
export interface SpecFormValues {
  sourceId: string
  adapter: string
  name: string
  /** Khóa → giá trị: enum là JSON của lựa chọn, số là chuỗi, boolean là 'true'/'false'. */
  params: Record<string, string>
  primaryName: string
  primaryType: 'continuous' | 'discrete'
  primaryMin: string
  primaryMax: string
  /** Giá trị rời rạc, ngăn bởi dấu phẩy. */
  primaryValues: string
  primaryUnit: string
  displayName: string
  description: string
  realism: Realism
  /** Mỗi dòng `level: nhãn`. */
  levelLabels: string
}

export const EMPTY_FORM: SpecFormValues = {
  sourceId: '',
  adapter: '',
  name: '',
  params: {},
  primaryName: '',
  primaryType: 'continuous',
  primaryMin: '',
  primaryMax: '',
  primaryValues: '',
  primaryUnit: '',
  displayName: '',
  description: '',
  realism: 'medium',
  levelLabels: '',
}

function paramText(value: JsonValue): string {
  return typeof value === 'number' || typeof value === 'boolean'
    ? String(value)
    : JSON.stringify(value)
}

/** Điền form từ spec có sẵn. Enum lưu dạng JSON để giữ kiểu (`norm` có cả "inf" lẫn 2). */
export function prefillFrom(
  spec: AttackSpecAdminView,
  fields: readonly ParamField[] = [],
): SpecFormValues {
  const enumKeys = new Set(fields.filter((f) => f.kind === 'enum').map((f) => f.key))
  const params = Object.fromEntries(
    Object.entries(spec.fixed_params).map(([key, value]) => [
      key,
      enumKeys.has(key) ? JSON.stringify(value) : paramText(value),
    ]),
  )
  const p = spec.primary_param
  return {
    sourceId: spec.id,
    adapter: adapterOf(spec),
    name: spec.name,
    params,
    primaryName: p.name,
    primaryType: p.type,
    primaryMin: String(p.min),
    primaryMax: String(p.max),
    primaryValues: (p.values ?? []).join(', '),
    primaryUnit: p.unit,
    displayName: spec.metadata?.display_name ?? '',
    description: spec.metadata?.description ?? '',
    realism: spec.metadata?.realism ?? 'medium',
    levelLabels: Object.entries(spec.metadata?.level_labels ?? {})
      .map(([level, label]) => `${level}: ${label}`)
      .join('\n'),
  }
}

/** Giá trị enum của ô chọn khi chưa có giá trị: chuẩn hóa JSON để so khớp `<option value>`. */
export function enumValue(raw: string | undefined): string {
  if (raw === undefined || raw === '') return ''
  try {
    return JSON.stringify(JSON.parse(raw) as JsonValue)
  } catch {
    return raw
  }
}

// ---------------------------------------------------------------- Dựng body

/** Lỗi theo trường: khóa là tên trường của form (`params.<khóa>` cho tham số). */
export type FormErrors = Partial<Record<string, string>>

export type BuildResult =
  | { ok: true; body: AttackSpecCreate['body']; metadata: AttackSpecMetadata }
  | { ok: false; errors: FormErrors }

const NAME_PATTERN = /^[a-z][a-z0-9_]*$/

function parseNumber(raw: string): number | null {
  if (raw.trim() === '') return null
  const value = Number(raw.trim())
  return Number.isFinite(value) ? value : null
}

function rangeMessage(field: Extract<ParamField, { kind: 'number' }>): string {
  const parts: string[] = []
  if (field.min !== undefined) parts.push(`${field.exclusiveMin ? '>' : '≥'} ${field.min}`)
  if (field.max !== undefined) parts.push(`${field.exclusiveMax ? '<' : '≤'} ${field.max}`)
  return `Nhập ${field.integer ? 'số nguyên' : 'số'}${parts.length ? ` ${parts.join(' và ')}` : ''}.`
}

function paramValue(field: ParamField, raw: string | undefined): JsonValue | undefined | Error {
  if (raw === undefined || raw === '') {
    return field.required ? new Error('Bắt buộc.') : undefined
  }
  if (field.kind === 'boolean') return raw === 'true'
  if (field.kind === 'enum') {
    try {
      const value = JSON.parse(raw) as JsonValue
      const known = field.options.some((o) => JSON.stringify(o) === JSON.stringify(value))
      return known ? value : new Error('Chọn một giá trị trong danh sách.')
    } catch {
      return new Error('Chọn một giá trị trong danh sách.')
    }
  }
  const value = parseNumber(raw)
  const bad =
    value === null ||
    (field.integer && !Number.isInteger(value)) ||
    (field.min !== undefined && (field.exclusiveMin ? value <= field.min : value < field.min)) ||
    (field.max !== undefined && (field.exclusiveMax ? value >= field.max : value > field.max))
  return bad ? new Error(rangeMessage(field)) : value
}

/** `level: nhãn` mỗi dòng → `level_labels`; dòng sai trả lỗi. */
export function parseLevelLabels(text: string): Record<string, string> | Error {
  const labels: Record<string, string> = {}
  const seen = new Set<number>()
  for (const line of text.split('\n')) {
    if (line.trim() === '') continue
    const at = line.indexOf(':')
    const level = at < 0 ? null : parseNumber(line.slice(0, at))
    const label = at < 0 ? '' : line.slice(at + 1).trim()
    if (level === null || label === '') {
      return new Error(`Dòng "${line.trim()}" chưa đúng dạng "level: nhãn", ví dụ "1: nhẹ".`)
    }
    if (seen.has(level)) return new Error(`Level ${level} bị lặp.`)
    seen.add(level)
    labels[String(level)] = label
  }
  return labels
}

export interface BuildContext {
  adapter: AttackAdapterInfo | undefined
  fields: readonly ParamField[]
  /** Spec nguồn ("Sao chép từ"); trường không có trên form lấy từ đây. */
  source: AttackSpecAdminView | undefined
  catalog: readonly AttackSpecAdminView[]
}

/** Thông báo khi adapter kiểu attack chưa có spec nguồn cùng adapter. */
export const NEEDS_SOURCE =
  'Adapter kiểu attack cần chọn "Sao chép từ" một spec cùng adapter: lớp ART, access và chi phí lấy từ spec đó.'

/**
 * Body của `POST /admin/attack-specs`. Trường không có trên form (`access`, `art_class`,
 * `cost_model`, `requires_training`, `training`) lấy từ spec nguồn cùng adapter; corruption và
 * occlusion không có nguồn thì dùng mặc định (không áp dụng, chỉ CPU). Người dùng chốt 2026-10-11.
 */
export function buildCreate(values: SpecFormValues, ctx: BuildContext): BuildResult {
  const errors: FormErrors = {}
  const { adapter, source } = ctx
  if (!adapter) errors.adapter = 'Chọn adapter.'
  const sameAdapter = source && adapter && adapterOf(source) === adapter.name ? source : undefined
  if (adapter?.kind === 'attack' && !sameAdapter) errors.sourceId = NEEDS_SOURCE

  const name = values.name.trim()
  if (!NAME_PATTERN.test(name)) {
    errors.name = 'Chữ thường, số và dấu gạch dưới, bắt đầu bằng chữ (ví dụ snow_light).'
  }

  const fixed: Record<string, JsonValue> = {}
  for (const field of ctx.fields) {
    const value = paramValue(field, values.params[field.key])
    if (value instanceof Error) errors[`params.${field.key}`] = value.message
    else if (value !== undefined) fixed[field.key] = value
  }

  const min = parseNumber(values.primaryMin)
  const max = parseNumber(values.primaryMax)
  if (values.primaryName.trim() === '') errors.primaryName = 'Bắt buộc.'
  if (values.primaryUnit.trim() === '') errors.primaryUnit = 'Bắt buộc.'
  if (min === null) errors.primaryMin = 'Nhập một số.'
  if (max === null) errors.primaryMax = 'Nhập một số.'
  if (min !== null && max !== null && min >= max) errors.primaryMax = 'Phải lớn hơn mức nhỏ nhất.'
  let levels: number[] | null = null
  if (values.primaryType === 'discrete') {
    const parsed = values.primaryValues
      .split(',')
      .filter((v) => v.trim() !== '')
      .map(parseNumber)
    if (parsed.length === 0 || parsed.some((v) => v === null)) {
      errors.primaryValues = 'Nhập các level, ngăn bởi dấu phẩy, ví dụ 1, 2, 3.'
    } else {
      levels = parsed as number[]
      if (min !== null && max !== null && levels.some((v) => v < min || v > max)) {
        errors.primaryValues = 'Mọi level phải nằm trong khoảng nhỏ nhất – lớn nhất.'
      }
    }
  }

  const labels = parseLevelLabels(values.levelLabels)
  if (labels instanceof Error) errors.levelLabels = labels.message
  if (values.displayName.trim() === '') errors.displayName = 'Bắt buộc.'
  if (values.description.trim() === '') errors.description = 'Bắt buộc.'

  if (Object.keys(errors).length > 0 || !adapter || labels instanceof Error) {
    return { ok: false, errors }
  }
  const corruptionLike = adapter.kind !== 'attack'
  const body: AttackSpecCreate['body'] = {
    schema_version: 1,
    name,
    version: nextVersion(name, ctx.catalog),
    kind: adapter.kind,
    access: sameAdapter ? sameAdapter.access : 'not_applicable',
    art_class: sameAdapter ? sameAdapter.art_class : null,
    primary_param: {
      name: values.primaryName.trim(),
      type: values.primaryType,
      min: min ?? 0,
      max: max ?? 0,
      values: levels,
      unit: values.primaryUnit.trim(),
    },
    fixed_params: fixed,
    cost_model: sameAdapter
      ? sameAdapter.cost_model
      : { passes_per_image: null, cpu_only: corruptionLike },
    requires_gradients: adapter.requires_gradients,
    // Spec nguồn ghi `adapter: null` (spec seed) thì giữ null: adapter suy ra vẫn là adapter này.
    adapter: sameAdapter ? sameAdapter.adapter : adapter.name,
  }
  if (sameAdapter?.requires_training) {
    body.requires_training = true
    body.training = sameAdapter.training
  }
  return {
    ok: true,
    body,
    metadata: {
      display_name: values.displayName.trim(),
      description: values.description.trim(),
      realism: values.realism,
      level_labels: labels,
    },
  }
}

// ---------------------------------------------------------------- Lỗi từ server

const TOP_FIELDS: Record<string, string> = {
  name: 'name',
  version: 'name',
  adapter: 'adapter',
  display_name: 'displayName',
  description: 'description',
  realism: 'realism',
  level_labels: 'levelLabels',
}

const PRIMARY_FIELDS: Record<string, string> = {
  name: 'primaryName',
  type: 'primaryType',
  min: 'primaryMin',
  max: 'primaryMax',
  values: 'primaryValues',
  unit: 'primaryUnit',
}

/** Trường của form ứng với `FieldError.path` của lỗi 422 (`body.fixed_params.norm` → `params.norm`). */
export function formFieldOf(path: string): string | null {
  const parts = path.split('.')
  if (parts[0] === 'body' || parts[0] === 'metadata') parts.shift()
  const [key = '', sub = ''] = parts
  if (key === 'fixed_params') return sub ? `params.${sub}` : null
  if (key === 'primary_param') return PRIMARY_FIELDS[sub] ?? 'primaryMin'
  return TOP_FIELDS[key] ?? null
}
