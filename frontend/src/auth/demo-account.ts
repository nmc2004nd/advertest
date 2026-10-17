import type { LoginRequest } from '@/contracts/schemas'

/** Tài khoản demo lấy từ biến build `VITE_DEMO_*`; `null` khi thiếu email hoặc mật khẩu. */
export function demoAccount(env: Partial<ImportMetaEnv> = import.meta.env): LoginRequest | null {
  const email = env.VITE_DEMO_EMAIL?.trim()
  const password = env.VITE_DEMO_PASSWORD
  return email && password ? { email, password } : null
}
