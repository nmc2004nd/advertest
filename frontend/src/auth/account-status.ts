import type { ErrorCode } from '@/contracts/schemas'

/** Mã lỗi đăng nhập của tài khoản chưa `active`: đưa tới trang /pending thay vì báo trên form. */
export const ACCOUNT_STATUS_CODES = [
  'account_pending',
  'account_rejected',
  'account_disabled',
] as const satisfies readonly ErrorCode[]

export type AccountStatusCode = (typeof ACCOUNT_STATUS_CODES)[number]

export function isAccountStatusCode(code: string): code is AccountStatusCode {
  return (ACCOUNT_STATUS_CODES as readonly string[]).includes(code)
}
