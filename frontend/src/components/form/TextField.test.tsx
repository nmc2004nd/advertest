import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import { TextField } from './TextField'

describe('TextField', () => {
  it('có nhãn gắn với ô nhập, font 16px', () => {
    const html = renderToStaticMarkup(<TextField id="email" label="Email" type="email" />)
    expect(html).toContain('<label for="email"')
    expect(html).toContain('text-base')
    expect(html).not.toContain('aria-invalid="')
  })

  it('lỗi hiển thị cạnh ô và gắn qua aria-describedby', () => {
    const html = renderToStaticMarkup(<TextField id="email" label="Email" error="Sai định dạng" />)
    expect(html).toContain('aria-invalid="true"')
    expect(html).toContain('aria-describedby="email-loi"')
    expect(html).toContain('id="email-loi"')
    expect(html).toContain('Sai định dạng')
  })
})
