/**
 * Trạng thái mở của tooltip thuật ngữ (requirements.md Phase R3, mục Thuật ngữ): hover, focus hoặc
 * chạm thì mở; Esc đóng (WCAG 1.4.13: tắt được mà không phải rời chuột hay focus).
 */
export type TermEvent = 'enter' | 'leave' | 'focus' | 'blur' | 'tap' | 'escape'

export interface TermState {
  hover: boolean
  focus: boolean
  /** Chạm hoặc bấm: lần đầu ghim mở (chạm cũng làm focus), lần sau đóng. */
  pinned: boolean
  /** Esc đã đóng: giữ đóng cho tới khi rời hẳn rồi quay lại. */
  dismissed: boolean
}

export const TERM_CLOSED: TermState = {
  hover: false,
  focus: false,
  pinned: false,
  dismissed: false,
}

export function termReducer(state: TermState, event: TermEvent): TermState {
  switch (event) {
    case 'enter':
      return { ...state, hover: true, dismissed: state.focus && state.dismissed }
    case 'leave':
      return { ...state, hover: false, pinned: false }
    case 'focus':
      return { ...state, focus: true, dismissed: state.hover && state.dismissed }
    case 'blur':
      return { ...state, focus: false, pinned: false, dismissed: state.hover && state.dismissed }
    case 'tap':
      return state.pinned
        ? { ...state, pinned: false, dismissed: true }
        : { ...state, pinned: true, dismissed: false }
    case 'escape':
      return { ...state, pinned: false, dismissed: true }
  }
}

export function termOpen(state: TermState): boolean {
  return !state.dismissed && (state.hover || state.focus || state.pinned)
}
