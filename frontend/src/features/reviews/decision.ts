/**
 * Khung quyết định của reviewer (requirements.md Phase 8, mục Danh sách kiểm tra trước khi chấp
 * nhận và Quyết định; chốt ở kickoff): server kiểm checklist trạng thái (409) và trường nhập
 * (422); giao diện khóa nút "Chấp nhận" và nêu lý do trước khi gửi.
 */
import type {
  ChecklistItem,
  ModelVerdict,
  PassCriterion,
  ReviewDecision,
  ReviewDecisionInput,
  ReviewView,
} from '@/contracts/api'

export interface DecisionForm {
  conclusion: string
  mitigation: string
  modelVerdict: ModelVerdict | ''
  inconclusiveJustification: string
}

export const EMPTY_DECISION: DecisionForm = {
  conclusion: '',
  mitigation: '',
  modelVerdict: '',
  inconclusiveJustification: '',
}

export const CHECKLIST_LABEL: Record<ChecklistItem['code'], string> = {
  protocol_not_dev: 'Protocol không phải bản phát triển',
  required_cases_reviewed: 'Mọi case bắt buộc đã có verdict',
}

export function hasInconclusive(review: ReviewView): boolean {
  return review.criteria_results.some((c) => c.status === 'inconclusive')
}

/** Lý do "Chấp nhận" còn bị khóa: checklist của server, rồi các ô bắt buộc của form. */
export function approveBlockers(review: ReviewView, form: DecisionForm): string[] {
  const reasons = review.checklist
    .filter((item) => !item.satisfied)
    .map((item) => `${CHECKLIST_LABEL[item.code]}: ${item.detail}`)
  if (!form.conclusion.trim()) reasons.push('Chưa có kết luận')
  if (!form.mitigation.trim()) reasons.push('Chưa có biện pháp khắc phục')
  if (!form.modelVerdict) reasons.push('Chưa chọn kết luận về model')
  if (hasInconclusive(review) && !form.inconclusiveJustification.trim()) {
    reasons.push('Có tiêu chí chưa kết luận: cần giải trình')
  }
  return reasons
}

/** `changes_requested` và `reject` chỉ cần kết luận (lý do). */
export function otherBlockers(form: DecisionForm): string[] {
  return form.conclusion.trim() ? [] : ['Chưa có kết luận (lý do)']
}

export function decisionBody(decision: ReviewDecision, form: DecisionForm): ReviewDecisionInput {
  const text = (value: string) => value.trim() || null
  return {
    decision,
    conclusion: form.conclusion.trim(),
    mitigation: text(form.mitigation),
    model_verdict: form.modelVerdict || null,
    inconclusive_justification: text(form.inconclusiveJustification),
  }
}

export function criterionText(c: PassCriterion): string {
  const target = c.class_filter ? ` (class ${c.class_filter})` : ''
  return c.kind === 'max_drop_at_level'
    ? `${c.attack_spec_name}: ${c.threshold_kind}${target} tại level ${c.level} ≤ ${c.threshold}`
    : `${c.attack_spec_name}: điểm gãy (${c.threshold_kind} ${c.threshold}${target}) ≥ ${c.level}`
}
