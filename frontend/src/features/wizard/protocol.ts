/**
 * Attack bắt buộc của protocol trong wizard (requirements.md Phase 8, Frontend engineer; plan task
 * 24): chọn protocol thì attack bắt buộc được thêm và khóa; level bắt buộc không xóa được; ngưỡng
 * tìm kiếm điền sẵn và khóa. Server vẫn kiểm tra tuân thủ (`compliance`), giao diện chỉ giúp không
 * cấu hình sai.
 */
import type { AttackSpec, ComplianceItem, ProtocolBody } from '@/contracts/api'

import { addLevel } from './levels'
import { DEFAULT_COARSE_N, DEFAULT_SUBSET_SIZE, type SearchDraft } from './search'
import type { AttackDraft, AttackMode } from './state'

export interface RequiredLock {
  attackSpecId: string
  specSha256: string
  name: string
  requiresTraining: boolean
  mode: AttackMode
  /** Level bắt buộc (quét lưới); rỗng với tìm ngưỡng. */
  levels: number[]
  /** Cấu hình tìm ngưỡng tối thiểu (ngưỡng bị khóa; dải, tol, bootstrap là mức tối thiểu). */
  search: SearchDraft | null
}

/** Attack bắt buộc tra trong catalog theo tên và `spec_sha256`; `missing` là attack không còn
 * version đó trong catalog (không tuân thủ được). */
export function requiredLocks(
  body: ProtocolBody,
  specs: AttackSpec[],
): { locks: RequiredLock[]; missing: string[] } {
  const locks: RequiredLock[] = []
  const missing: string[] = []
  for (const required of body.required_attacks) {
    const spec = specs.find(
      (s) => s.name === required.attack_spec_name && s.spec_sha256 === required.spec_sha256,
    )
    if (!spec) {
      missing.push(required.attack_spec_name)
      continue
    }
    const search = required.search
    locks.push({
      attackSpecId: spec.id,
      specSha256: spec.spec_sha256,
      name: spec.name,
      requiresTraining: spec.requires_training === true,
      mode: required.mode,
      levels: [...(required.grid?.levels ?? [])].sort((a, b) => a - b),
      search: search
        ? {
            thresholdKind: search.threshold_kind,
            threshold: search.threshold,
            classFilter: search.class_filter ?? null,
            lo: search.lo,
            hi: search.hi,
            tol: search.max_tol,
            tolEdited: true, // giữ đúng max_tol; đổi dải không tính lại
            coarseN: DEFAULT_COARSE_N,
            subsetSize: DEFAULT_SUBSET_SIZE,
            bootstrapSamples: search.min_bootstrap_samples ?? 200,
          }
        : null,
    })
  }
  return { locks, missing }
}

/** `levels` cộng mọi level bắt buộc còn thiếu (sắp tăng dần). */
export function withRequiredLevels(levels: number[], required: number[]): number[] {
  return required.reduce(
    (all, level) => (all.includes(level) ? all : addLevel(all, level)),
    [...levels],
  )
}

/** Ngưỡng khóa theo protocol; dải chỉ được rộng hơn, tol nhỏ hơn, bootstrap nhiều hơn. */
function lockedSearch(current: SearchDraft | null, lock: SearchDraft): SearchDraft {
  if (current === null) return lock
  return {
    ...current,
    thresholdKind: lock.thresholdKind,
    threshold: lock.threshold,
    classFilter: lock.classFilter,
    lo: Math.min(current.lo, lock.lo),
    hi: Math.max(current.hi, lock.hi),
    tol: Math.min(current.tol, lock.tol),
    bootstrapSamples: Math.max(current.bootstrapSamples, lock.bootstrapSamples),
  }
}

/** Thêm attack bắt buộc còn thiếu và đưa attack đã có về đúng yêu cầu (không bỏ attack khác). */
export function applyLocks(attacks: AttackDraft[], locks: RequiredLock[]): AttackDraft[] {
  const out = [...attacks]
  for (const lock of locks) {
    const index = out.findIndex((a) => a.attackSpecId === lock.attackSpecId)
    const current = index >= 0 ? out[index] : null
    const next: AttackDraft = {
      attackSpecId: lock.attackSpecId,
      specSha256: lock.specSha256,
      requiresTraining: lock.requiresTraining,
      trainingSliceId: current?.trainingSliceId ?? null,
      mode: lock.mode,
      levels:
        lock.mode === 'grid'
          ? withRequiredLevels(current?.levels ?? [], lock.levels)
          : (current?.levels ?? []),
      search:
        lock.mode === 'search' && lock.search
          ? lockedSearch(current?.search ?? null, lock.search)
          : (current?.search ?? null),
    }
    if (index >= 0) out[index] = next
    else out.push(next)
  }
  return out
}

/** Trường tìm ngưỡng bị khóa theo protocol (bỏ khỏi thay đổi của người dùng). */
export const LOCKED_SEARCH_FIELDS = ['thresholdKind', 'threshold', 'classFilter'] as const

export function withoutLockedFields(patch: Partial<SearchDraft>): Partial<SearchDraft> {
  const locked = new Set<string>(LOCKED_SEARCH_FIELDS)
  return Object.fromEntries(
    Object.entries(patch).filter(([key]) => !locked.has(key)),
  ) as Partial<SearchDraft>
}

export const LOCK_LABEL = 'Theo protocol'

/** Nhãn của từng mục tuân thủ (`ComplianceCode`). */
export const COMPLIANCE_LABEL: Record<ComplianceItem['code'], string> = {
  protocol_active: 'Protocol đang dùng được',
  attack_present: 'Có attack bắt buộc',
  spec_sha256: 'Đúng version attack',
  mode: 'Đúng chế độ',
  grid_levels: 'Đủ level bắt buộc',
  search_threshold: 'Đúng ngưỡng tìm kiếm',
  search_range: 'Dải tìm kiếm đủ rộng',
  search_tol: 'Độ chính xác đủ nhỏ',
  search_bootstrap: 'Đủ mẫu bootstrap',
  min_slice_size: 'Slice đủ lớn',
  model_gradients: 'Model hỗ trợ gradient',
}
