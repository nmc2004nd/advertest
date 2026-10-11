import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import { GLOSSARY, type GlossaryKey } from '@/copy/glossary'

import { Term } from './Term'
import { TERM_CLOSED, type TermEvent, termOpen, termReducer } from './term-state'

const run = (...events: TermEvent[]) => events.reduce(termReducer, TERM_CLOSED)

describe('bảng thuật ngữ (requirements.md Phase R3, mục Thuật ngữ)', () => {
  const REQUIRED: GlossaryKey[] = [
    'map',
    'ap50',
    'relative_drop',
    'breaking_point',
    'level',
    'white_box',
    'corruption',
    'occlusion',
    'patch',
    'slice',
    'protocol',
    'fingerprint',
    'exploration',
    'official',
  ]

  it('có đủ các mục bắt buộc', () => {
    expect(Object.keys(GLOSSARY)).toEqual(expect.arrayContaining(REQUIRED))
  })

  it.each(Object.entries(GLOSSARY))('%s: định nghĩa tối đa 2 câu', (_, entry) => {
    // Câu kết thúc bằng dấu chấm, chấm hỏi hoặc chấm than theo sau là khoảng trắng hoặc hết chuỗi.
    const sentences = entry.definition.split(/[.!?](?:\s|$)/).filter((s) => s.trim())
    expect(sentences.length).toBeGreaterThan(0)
    expect(sentences.length).toBeLessThanOrEqual(2)
  })
})

describe('Term: trạng thái tooltip', () => {
  it('Tab tới thì mở, Esc thì đóng', () => {
    expect(termOpen(run('focus'))).toBe(true)
    expect(termOpen(run('focus', 'escape'))).toBe(false)
  })

  it('rê chuột thì mở, rời thì đóng; Esc đóng cả khi đang rê', () => {
    expect(termOpen(run('enter'))).toBe(true)
    expect(termOpen(run('enter', 'leave'))).toBe(false)
    expect(termOpen(run('enter', 'escape'))).toBe(false)
  })

  it('sau Esc, rời focus rồi Tab lại thì mở lại', () => {
    expect(termOpen(run('focus', 'escape', 'blur', 'focus'))).toBe(true)
  })

  it('chạm: lần đầu mở (kể cả khi chạm làm focus), lần sau đóng', () => {
    expect(termOpen(run('tap'))).toBe(true)
    expect(termOpen(run('focus', 'tap'))).toBe(true)
    expect(termOpen(run('focus', 'tap', 'tap'))).toBe(false)
  })
})

describe('Term: render', () => {
  it('focus được, aria-describedby trỏ tới tooltip; đóng thì tooltip ẩn', () => {
    const html = renderToStaticMarkup(<Term term="relative_drop" />)
    expect(html).toContain('data-term="relative_drop"')
    expect(html).toContain('tabindex="0"')
    const describedBy = /aria-describedby="([^"]+)"/.exec(html)?.[1]
    expect(describedBy).toBeTruthy()
    expect(html).toMatch(new RegExp(`role="tooltip" id="${describedBy}" hidden`))
    expect(html).toContain(GLOSSARY.relative_drop.definition)
  })

  it('mở thì tooltip hiện; chữ trong câu có thể khác tên thuật ngữ', () => {
    const html = renderToStaticMarkup(
      <Term term="breaking_point" initial={run('focus')}>
        Điểm gãy
      </Term>,
    )
    expect(html).toMatch(/role="tooltip" id="[^"]+" class=/)
    expect(html).not.toMatch(/role="tooltip"[^>]*hidden/)
    expect(html).toContain('>Điểm gãy</span>')
  })
})
