/**
 * Form xây dựng protocol (requirements.md Phase 8, Frontend reviewer; plan task 30): trạng thái
 * thuần và chuyển sang `ProtocolBody`, kiểm tra cùng luật với contract (tên attack không trùng,
 * tiêu chí tham chiếu attack bắt buộc, `max_drop_at_level` tại level bắt buộc của attack quét lưới,
 * `min_breaking_point` cùng ngưỡng với tìm ngưỡng và `lo < level ≤ hi`). Kiểm tra cần catalog
 * (dải của spec, `MAX_RUNS`) để server báo (422).
 */
import { z } from 'zod'

import type { AttackSpec, ProtocolBody, ThresholdKind } from '@/contracts/api'

export type CriterionKind = 'max_drop_at_level' | 'min_breaking_point'

export interface AttackRow {
  name: string
  mode: 'grid' | 'search'
  /** Level quét lưới, ngăn bởi dấu phẩy. */
  levels: string
  thresholdKind: ThresholdKind
  /** Phần trăm (1–100). */
  threshold: string
  classFilter: string
  lo: string
  hi: string
  maxTol: string
  minBootstrap: string
}

export interface CriterionRow {
  kind: CriterionKind
  attackName: string
  level: string
  thresholdKind: ThresholdKind
  threshold: string
  classFilter: string
}

export interface ProtocolForm {
  name: string
  description: string
  minSliceSize: string
  casesPerAttack: string
  forbidDirty: boolean
  attacks: AttackRow[]
  criteria: CriterionRow[]
}

export const EMPTY_ATTACK: AttackRow = {
  name: '',
  mode: 'grid',
  levels: '',
  thresholdKind: 'relative_drop',
  threshold: '20',
  classFilter: '',
  lo: '',
  hi: '',
  maxTol: '',
  minBootstrap: '200',
}

export const EMPTY_CRITERION: CriterionRow = {
  kind: 'max_drop_at_level',
  attackName: '',
  level: '',
  thresholdKind: 'relative_drop',
  threshold: '20',
  classFilter: '',
}

export const EMPTY_FORM: ProtocolForm = {
  name: '',
  description: '',
  minSliceSize: '300',
  casesPerAttack: '5',
  forbidDirty: true,
  attacks: [{ ...EMPTY_ATTACK }],
  criteria: [{ ...EMPTY_CRITERION }],
}

const num = (raw: string) => (raw.trim() === '' ? Number.NaN : Number(raw))
const pct = (raw: string) => num(raw) / 100
const round = (value: number) => Number(value.toFixed(6))

/** Form từ một body đã có (tạo version mới điền sẵn bản mới nhất). */
export function formOf(name: string, body: ProtocolBody): ProtocolForm {
  const percent = (v: number) => String(round(v * 100))
  return {
    name,
    description: body.description,
    minSliceSize: String(body.min_slice_size),
    casesPerAttack: String(body.cases_to_review_per_attack ?? 5),
    forbidDirty: body.forbid_dirty_runs ?? true,
    attacks: body.required_attacks.map((a) => ({
      ...EMPTY_ATTACK,
      name: a.attack_spec_name,
      mode: a.mode,
      levels: (a.grid?.levels ?? []).join(', '),
      thresholdKind: a.search?.threshold_kind ?? 'relative_drop',
      threshold: a.search ? percent(a.search.threshold) : EMPTY_ATTACK.threshold,
      classFilter: a.search?.class_filter ?? '',
      lo: a.search ? String(a.search.lo) : '',
      hi: a.search ? String(a.search.hi) : '',
      maxTol: a.search ? String(a.search.max_tol) : '',
      minBootstrap: String(a.search?.min_bootstrap_samples ?? 200),
    })),
    criteria: body.pass_criteria.map((c) => ({
      kind: c.kind,
      attackName: c.attack_spec_name,
      level: String(c.level),
      thresholdKind: c.threshold_kind,
      threshold: percent(c.threshold),
      classFilter: c.class_filter ?? '',
    })),
  }
}

const positiveInt = z.number().int().positive()
const unit = z.number().gt(0).lte(1)

export type BuildResult =
  { ok: true; name: string; body: ProtocolBody } | { ok: false; errors: Record<string, string> }

/** Body gửi lên, hoặc lỗi theo đường dẫn của form (`attacks.0.levels`, `criteria.1.level`...). */
export function buildProtocol(form: ProtocolForm, specs: AttackSpec[]): BuildResult {
  const errors: Record<string, string> = {}
  const fail = (path: string, message: string) => {
    errors[path] ??= message
  }
  if (!form.name.trim()) fail('name', 'Nhập tên protocol')
  if (!form.description.trim()) fail('description', 'Nhập mục đích của protocol')
  const minSlice = num(form.minSliceSize)
  if (!positiveInt.safeParse(minSlice).success) fail('minSliceSize', 'Số nguyên dương')
  const cases = num(form.casesPerAttack)
  if (!positiveInt.safeParse(cases).success) fail('casesPerAttack', 'Số nguyên dương')
  if (form.attacks.length === 0) fail('attacks', 'Cần ít nhất một attack bắt buộc')
  if (form.criteria.length === 0) fail('criteria', 'Cần ít nhất một tiêu chí')

  const seen = new Set<string>()
  const attacks = form.attacks.map((a, i) => {
    const path = `attacks.${i}`
    const spec = specs.find((s) => s.name === a.name)
    if (!spec) fail(`${path}.name`, 'Chọn attack trong catalog')
    if (seen.has(a.name)) fail(`${path}.name`, 'Mỗi attack chỉ một lần (một chế độ)')
    seen.add(a.name)
    if (a.mode === 'grid') {
      const levels = a.levels
        .split(/[,\s]+/)
        .filter(Boolean)
        .map(Number)
      if (levels.length === 0 || levels.some((l) => !Number.isFinite(l))) {
        fail(`${path}.levels`, 'Nhập level, ngăn bởi dấu phẩy')
      } else if (new Set(levels).size !== levels.length) {
        fail(`${path}.levels`, 'Level bị trùng')
      }
      return {
        attack_spec_name: a.name,
        spec_sha256: spec?.spec_sha256 ?? '',
        mode: 'grid' as const,
        grid: { levels },
        search: null,
      }
    }
    if (spec?.requires_training)
      fail(`${path}.mode`, 'Attack cần train patch không tìm ngưỡng được')
    const threshold = pct(a.threshold)
    if (!unit.safeParse(threshold).success) fail(`${path}.threshold`, 'Ngưỡng trong (0, 100]%')
    const lo = num(a.lo)
    const hi = num(a.hi)
    const maxTol = num(a.maxTol)
    const minBootstrap = num(a.minBootstrap)
    if (!Number.isFinite(lo) || !Number.isFinite(hi) || lo >= hi) fail(`${path}.lo`, 'Cần lo < hi')
    if (!(maxTol > 0) || maxTol >= hi - lo) fail(`${path}.maxTol`, 'Cần 0 < max_tol < hi − lo')
    if (!z.number().int().min(0).max(1000).safeParse(minBootstrap).success) {
      fail(`${path}.minBootstrap`, 'Số nguyên 0–1000')
    }
    return {
      attack_spec_name: a.name,
      spec_sha256: spec?.spec_sha256 ?? '',
      mode: 'search' as const,
      grid: null,
      search: {
        threshold_kind: a.thresholdKind,
        threshold,
        class_filter: a.classFilter.trim() || null,
        lo,
        hi,
        max_tol: maxTol,
        min_bootstrap_samples: minBootstrap,
      },
    }
  })

  const criteria = form.criteria.map((c, i) => {
    const path = `criteria.${i}`
    const attack = attacks.find((a) => a.attack_spec_name === c.attackName)
    const level = num(c.level)
    if (!attack) fail(`${path}.attackName`, 'Chọn một attack bắt buộc')
    if (!Number.isFinite(level)) fail(`${path}.level`, 'Nhập level')
    if (c.kind === 'max_drop_at_level') {
      if (attack && attack.mode !== 'grid') {
        fail(`${path}.kind`, 'Mức sụt tại level chỉ dùng với attack quét lưới')
      } else if (attack?.grid && !attack.grid.levels.includes(level)) {
        fail(`${path}.level`, 'Phải là một level bắt buộc của attack')
      }
      const threshold = pct(c.threshold)
      if (!unit.safeParse(threshold).success) fail(`${path}.threshold`, 'Ngưỡng trong (0, 100]%')
      return {
        kind: c.kind,
        attack_spec_name: c.attackName,
        level,
        threshold_kind: c.thresholdKind,
        threshold,
        class_filter: c.classFilter.trim() || null,
      }
    }
    // Điểm gãy: ngưỡng lấy theo cấu hình tìm ngưỡng của attack (contract bắt buộc trùng).
    const search = attack?.search
    if (attack && !search) fail(`${path}.kind`, 'Điểm gãy tối thiểu chỉ dùng với attack tìm ngưỡng')
    if (search && !(search.lo < level && level <= search.hi)) {
      fail(`${path}.level`, `Cần ${search.lo} < level ≤ ${search.hi}`)
    }
    return {
      kind: c.kind,
      attack_spec_name: c.attackName,
      level,
      threshold_kind: search?.threshold_kind ?? c.thresholdKind,
      threshold: search?.threshold ?? pct(c.threshold),
      class_filter: search?.class_filter ?? null,
    }
  })

  if (Object.keys(errors).length > 0) return { ok: false, errors }
  return {
    ok: true,
    name: form.name.trim(),
    body: {
      schema_version: 2,
      description: form.description.trim(),
      required_attacks: attacks,
      min_slice_size: minSlice,
      pass_criteria: criteria,
      cases_to_review_per_attack: cases,
      forbid_dirty_runs: form.forbidDirty,
    },
  }
}

/** Lỗi 422 của server (`body.required_attacks.0.spec_sha256`) thành đường dẫn của form. */
export function formPath(serverPath: string): string {
  return serverPath
    .replace(/^body\./, '')
    .replace(/^min_slice_size$/, 'minSliceSize')
    .replace(/^cases_to_review_per_attack$/, 'casesPerAttack')
    .replace(/^required_attacks\.(\d+)\.mode$/, 'attacks.$1.mode')
    .replace(/^required_attacks\.(\d+)(\..*)?$/, 'attacks.$1')
    .replace(/^required_attacks$/, 'attacks')
    .replace(/^pass_criteria\.(\d+)(\..*)?$/, 'criteria.$1')
    .replace(/^pass_criteria$/, 'criteria')
}

/** Đường dẫn form có chỗ hiển thị lỗi; lỗi khác (ví dụ của cả body) hiện ở đầu form. */
export function isShownPath(path: string): boolean {
  return /^(name|description|minSliceSize|casesPerAttack|attacks|criteria)$|^attacks\.\d+(\.mode)?$|^criteria\.\d+$/.test(
    path,
  )
}
