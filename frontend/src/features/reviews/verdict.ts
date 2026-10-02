/**
 * Verdict của failure case (requirements.md Phase 8, Frontend reviewer; plan task 29): nhãn và
 * phím tắt. `J`/`K` case sau/trước, `1`–`4` mức nghiêm trọng, `S`/`A`/`N` loại verdict,
 * `Ctrl+Enter` (hoặc `⌘+Enter`) lưu, `?` bảng phím tắt.
 */
import type {
  CaseSeverity,
  CaseVerdictInput,
  CaseVerdictKind,
  ExperimentDetail,
} from '@/contracts/api'

export const SEVERITIES: { value: CaseSeverity; label: string; key: string }[] = [
  { value: 'critical', label: 'Nghiêm trọng', key: '1' },
  { value: 'major', label: 'Lớn', key: '2' },
  { value: 'minor', label: 'Nhỏ', key: '3' },
  { value: 'acceptable', label: 'Chấp nhận được', key: '4' },
]

export const KINDS: { value: CaseVerdictKind; label: string; key: string }[] = [
  { value: 'safety_relevant', label: 'Ảnh hưởng an toàn', key: 'S' },
  { value: 'acceptable', label: 'Chấp nhận được', key: 'A' },
  { value: 'annotation_issue', label: 'Lỗi nhãn', key: 'N' },
]

export const SEVERITY_LABEL = Object.fromEntries(
  SEVERITIES.map((s) => [s.value, s.label]),
) as Record<CaseSeverity, string>
export const KIND_LABEL = Object.fromEntries(KINDS.map((k) => [k.value, k.label])) as Record<
  CaseVerdictKind,
  string
>

export const SHORTCUTS: [string, string][] = [
  ['J / K', 'Case sau / trước'],
  ['1 – 4', 'Mức nghiêm trọng (nghiêm trọng, lớn, nhỏ, chấp nhận được)'],
  ['S / A / N', 'Ảnh hưởng an toàn / chấp nhận được / lỗi nhãn'],
  ['Ctrl + Enter', 'Lưu verdict'],
  ['?', 'Hiện bảng phím tắt'],
]

export type ShortcutAction =
  | { type: 'next' }
  | { type: 'prev' }
  | { type: 'severity'; value: CaseSeverity }
  | { type: 'kind'; value: CaseVerdictKind }
  | { type: 'save' }
  | { type: 'help' }

export interface KeyLike {
  key: string
  ctrlKey: boolean
  metaKey: boolean
  altKey: boolean
  /** Phím gõ trong ô nhập: chỉ `Ctrl+Enter` có tác dụng. */
  inField: boolean
}

/** Hành động của một lần bấm phím; null khi không phải phím tắt. */
export function shortcutOf(event: KeyLike): ShortcutAction | null {
  if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) return { type: 'save' }
  if (event.inField || event.ctrlKey || event.metaKey || event.altKey) return null
  if (event.key === '?') return { type: 'help' }
  const key = event.key.toUpperCase()
  if (key === 'J') return { type: 'next' }
  if (key === 'K') return { type: 'prev' }
  const severity = SEVERITIES.find((s) => s.key === key)
  if (severity) return { type: 'severity', value: severity.value }
  const kind = KINDS.find((k) => k.key === key)
  if (kind) return { type: 'kind', value: kind.value }
  return null
}

/** Phần tử đang focus là ô nhập (phím chữ thuộc về ô nhập, không phải phím tắt). */
export function isTextField(target: EventTarget | null): boolean {
  if (!target || typeof (target as Element).tagName !== 'string') return false
  const element = target as HTMLElement
  return (
    ['INPUT', 'TEXTAREA', 'SELECT'].includes(element.tagName) || element.isContentEditable === true
  )
}

export interface VerdictDraft {
  severity: CaseSeverity | null
  kind: CaseVerdictKind | null
  mitigation: string
}

/** Body gửi đi, hoặc lý do chưa gửi được (cùng luật với contract: `safety_relevant` cần
 * mitigation). */
export function verdictBody(draft: VerdictDraft): { body: CaseVerdictInput } | { error: string } {
  if (!draft.severity) return { error: 'Chọn mức nghiêm trọng' }
  if (!draft.kind) return { error: 'Chọn loại verdict' }
  const mitigation = draft.mitigation.trim()
  if (draft.kind === 'safety_relevant' && !mitigation) {
    return { error: 'Verdict ảnh hưởng an toàn cần biện pháp khắc phục' }
  }
  return { body: { severity: draft.severity, kind: draft.kind, mitigation: mitigation || null } }
}

/** Danh sách case để chuyển J/K: case bắt buộc theo thứ tự trên trang review. */
export function neighbours(experiment: ExperimentDetail, caseId: string) {
  const ids = (experiment.review?.required_cases ?? []).map((c) => c.failure_case_id)
  const index = ids.indexOf(caseId)
  return {
    index,
    total: ids.length,
    prev: index > 0 ? ids[index - 1] : undefined,
    next: index >= 0 && index < ids.length - 1 ? ids[index + 1] : undefined,
  }
}

/** Áp phím tắt chọn mức nghiêm trọng hoặc loại verdict lên bản nháp; phím khác giữ nguyên. */
export function applyShortcut(draft: VerdictDraft, action: ShortcutAction): VerdictDraft {
  if (action.type === 'severity') return { ...draft, severity: action.value }
  if (action.type === 'kind') return { ...draft, kind: action.value }
  return draft
}
