import type { AttackAccess, AttackSpecAdminView } from '@/contracts/api'
import { rangeText } from '@/features/wizard/levels'

export const ACCESS_LABEL: Record<AttackAccess, string> = {
  white_box: 'White-box',
  black_box: 'Black-box',
  not_applicable: 'Không áp dụng',
}

/** Tham số chính và dải, ví dụ "eps: 0–32 1/255". */
export function primaryText(spec: AttackSpecAdminView): string {
  return `${spec.primary_param.name}: ${rangeText(spec.primary_param)}`
}

/** Tham số cố định dạng `khóa = giá trị` (giá trị JSON rút gọn). */
export function fixedParamLines(spec: AttackSpecAdminView): string[] {
  return Object.entries(spec.fixed_params).map(
    ([key, value]) => `${key} = ${JSON.stringify(value)}`,
  )
}
