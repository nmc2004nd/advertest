import type { AttackSpec } from '@/contracts/api'

import { adapterOf } from './spec-form'

export interface SpecChange {
  field: string
  before: string
  after: string
}

type Body = Pick<
  AttackSpec,
  | 'kind'
  | 'access'
  | 'art_class'
  | 'adapter'
  | 'primary_param'
  | 'fixed_params'
  | 'cost_model'
  | 'requires_gradients'
  | 'requires_training'
  | 'training'
>

function text(value: unknown): string {
  return value === undefined || value === null ? '—' : JSON.stringify(value)
}

/**
 * Khác biệt giữa spec chờ duyệt và version `active` cùng tên (requirements.md Phase R3, mục Reviewer
 * duyệt spec): từng trường của phần thân, tham số cố định so theo từng khóa.
 */
export function specChanges(before: Body, after: Body): SpecChange[] {
  const changes: SpecChange[] = []
  const add = (field: string, a: unknown, b: unknown) => {
    if (text(a) !== text(b)) changes.push({ field, before: text(a), after: text(b) })
  }
  add('adapter', adapterOf(before), adapterOf(after))
  add('kind', before.kind, after.kind)
  add('access', before.access, after.access)
  add('art_class', before.art_class, after.art_class)
  const pa = before.primary_param
  const pb = after.primary_param
  add(`primary_param.name`, pa.name, pb.name)
  add(`primary_param.type`, pa.type, pb.type)
  add(`primary_param.min`, pa.min, pb.min)
  add(`primary_param.max`, pa.max, pb.max)
  add(`primary_param.values`, pa.values ?? null, pb.values ?? null)
  add(`primary_param.unit`, pa.unit, pb.unit)
  const keys = new Set([...Object.keys(before.fixed_params), ...Object.keys(after.fixed_params)])
  for (const key of [...keys].sort()) {
    add(`fixed_params.${key}`, before.fixed_params[key], after.fixed_params[key])
  }
  add('cost_model', before.cost_model, after.cost_model)
  add('requires_gradients', before.requires_gradients, after.requires_gradients)
  add('requires_training', before.requires_training ?? false, after.requires_training ?? false)
  add('training', before.training ?? null, after.training ?? null)
  return changes
}
