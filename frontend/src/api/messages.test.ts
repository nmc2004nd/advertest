import { describe, expect, it } from 'vitest'

import { errorCodeValues } from '@/contracts/schemas'

import { ApiError } from './errors'
import { ERROR_MESSAGES, UNKNOWN_ERROR_MESSAGE, errorMessage } from './messages'

describe('thông điệp lỗi', () => {
  it('mọi ErrorCode trong contract có thông điệp tiếng Việt', () => {
    expect(Object.keys(ERROR_MESSAGES).sort()).toEqual([...errorCodeValues].sort())
    for (const code of errorCodeValues) expect(ERROR_MESSAGES[code].length).toBeGreaterThan(0)
  })

  it('lỗi nghiệp vụ giữ thông điệp của server, mã khác dùng thông điệp chung', () => {
    expect(errorMessage(new ApiError(409, 'conflict', 'Không thể duyệt'))).toBe('Không thể duyệt')
    expect(errorMessage(new ApiError(401, 'invalid_credentials', 'x'))).toBe(
      ERROR_MESSAGES.invalid_credentials,
    )
    expect(errorMessage(new Error('mạng'))).toBe(UNKNOWN_ERROR_MESSAGE)
  })
})
