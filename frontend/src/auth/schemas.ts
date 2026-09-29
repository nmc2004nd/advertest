import { z } from 'zod'

import { roleValues, type Role } from '@/contracts/schemas'

/**
 * Schema form (requirements.md Phase 4): cùng luật với contract (`Email`, `NewPassword`) để báo
 * lỗi ngay cạnh ô nhập; backend vẫn kiểm tra lại.
 */
const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/

export const emailField = z
  .string()
  .trim()
  .min(1, 'Nhập email')
  .max(254, 'Email quá dài')
  .regex(EMAIL_PATTERN, 'Email không hợp lệ')

export const newPasswordField = z
  .string()
  .min(10, 'Mật khẩu cần ít nhất 10 ký tự')
  .max(256, 'Mật khẩu quá dài')

const requiredText = (message: string, max = 200) =>
  z.string().trim().min(1, message).max(max, `Tối đa ${max} ký tự`)

function sameAsEmail(password: string, email: string): boolean {
  return password.trim().toLowerCase() === email.trim().toLowerCase()
}

export const loginSchema = z.object({
  email: emailField,
  password: z.string().min(1, 'Nhập mật khẩu'),
})

export const accessRequestSchema = z
  .object({
    full_name: requiredText('Nhập họ tên'),
    email: emailField,
    organization: z.string().trim().max(200, 'Tối đa 200 ký tự'),
    requested_role: z.enum(roleValues as readonly [Role, ...Role[]], { message: 'Chọn vai trò' }),
    reason: requiredText('Cho biết lý do cần truy cập', 2000),
    password: newPasswordField,
    password_confirm: z.string(),
  })
  .refine((v) => !sameAsEmail(v.password, v.email), {
    path: ['password'],
    message: 'Mật khẩu không được trùng email',
  })
  .refine((v) => v.password === v.password_confirm, {
    path: ['password_confirm'],
    message: 'Mật khẩu nhập lại không khớp',
  })

export const passwordChangeSchema = z
  .object({
    current_password: z.string().min(1, 'Nhập mật khẩu hiện tại'),
    new_password: newPasswordField,
    new_password_confirm: z.string(),
  })
  .refine((v) => v.new_password === v.new_password_confirm, {
    path: ['new_password_confirm'],
    message: 'Mật khẩu nhập lại không khớp',
  })

export const passwordResetSchema = z
  .object({
    new_password: newPasswordField,
    new_password_confirm: z.string(),
  })
  .refine((v) => v.new_password === v.new_password_confirm, {
    path: ['new_password_confirm'],
    message: 'Mật khẩu nhập lại không khớp',
  })
