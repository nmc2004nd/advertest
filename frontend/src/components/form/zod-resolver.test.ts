import { describe, expect, it } from 'vitest'
import { z } from 'zod'

import { zodResolver } from './zod-resolver'

const schema = z.object({
  email: z.string().email('Email không hợp lệ'),
  password: z.string().min(10, 'Tối thiểu 10 ký tự'),
  profile: z.object({ name: z.string().min(1, 'Bắt buộc') }),
})

const resolve = (values: unknown) =>
  zodResolver(schema)(values as z.input<typeof schema>, undefined, {
    fields: {},
    shouldUseNativeValidation: false,
  })

describe('zodResolver', () => {
  it('dữ liệu hợp lệ trả values, không có lỗi', async () => {
    const values = { email: 'a@x.com', password: '1234567890', profile: { name: 'A' } }
    await expect(resolve(values)).resolves.toEqual({ values, errors: {} })
  })

  it('lỗi theo đường dẫn trường, kể cả trường lồng nhau', async () => {
    const result = await resolve({ email: 'x', password: 'ngan', profile: { name: '' } })
    expect(result.values).toEqual({})
    expect(result.errors).toMatchObject({
      email: { message: 'Email không hợp lệ' },
      password: { message: 'Tối thiểu 10 ký tự' },
      profile: { name: { message: 'Bắt buộc' } },
    })
  })
})
