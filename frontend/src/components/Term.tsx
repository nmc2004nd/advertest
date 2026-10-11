import { type ReactNode, useEffect, useId, useReducer } from 'react'

import { GLOSSARY, type GlossaryKey } from '@/copy/glossary'

import { TERM_CLOSED, termOpen, termReducer, type TermState } from './term-state'

/**
 * Thuật ngữ có gạch chân chấm; hover, focus (Tab) hoặc chạm thì mở định nghĩa trong tooltip, Esc
 * đóng (requirements.md Phase R3, mục Thuật ngữ). Tooltip luôn có trong DOM để `aria-describedby`
 * trỏ tới được; khi đóng thì ẩn.
 */
export function Term({
  term,
  children,
  initial = TERM_CLOSED,
}: {
  term: GlossaryKey
  /** Chữ hiện trong câu; mặc định là `term` của bảng thuật ngữ. */
  children?: ReactNode
  /** Chỉ dùng cho test render tĩnh. */
  initial?: TermState
}) {
  const entry = GLOSSARY[term]
  const id = useId()
  const [state, dispatch] = useReducer(termReducer, initial)
  const open = termOpen(state)

  // Esc đóng cả khi tooltip mở do rê chuột (focus đang ở chỗ khác).
  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') dispatch('escape')
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open])

  return (
    <span
      className="relative inline-block"
      onMouseEnter={() => dispatch('enter')}
      onMouseLeave={() => dispatch('leave')}
    >
      <span
        data-term={term}
        tabIndex={0}
        aria-describedby={id}
        onFocus={() => dispatch('focus')}
        onBlur={() => dispatch('blur')}
        onClick={() => dispatch('tap')}
        className="cursor-help rounded-sm underline decoration-dotted decoration-from-font underline-offset-[3px] focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
      >
        {children ?? entry.term}
      </span>
      <span
        role="tooltip"
        id={id}
        hidden={!open}
        className="absolute top-full left-0 z-50 mt-1.5 w-max max-w-[min(18rem,calc(100vw-2rem))] rounded-md border border-line bg-popover px-3 py-2 text-left text-[13px] leading-5 font-normal text-popover-foreground normal-case shadow-lg"
      >
        <b className="font-semibold">{entry.term}.</b> {entry.definition}
      </span>
    </span>
  )
}
