import { useMutation } from '@tanstack/react-query'
import { Link, useParams } from 'react-router'
import type { z } from 'zod'

import { apiSend } from '@/api/client'
import { errorMessage } from '@/api/messages'
import { passwordResetSchema } from '@/auth/schemas'
import { FormAlert } from '@/components/FormAlert'
import { TextField } from '@/components/form/TextField'
import { useZodForm } from '@/components/form/useZodForm'
import { Button } from '@/components/ui/button'
import { PublicLayout } from '@/layout/PublicLayout'

type Values = z.output<typeof passwordResetSchema>

/** Đặt lại mật khẩu bằng link một lần do admin tạo; xong thì mọi phiên cũ bị thu hồi. */
export function ResetPasswordPage() {
  const { token = '' } = useParams()
  const form = useZodForm(passwordResetSchema, {
    defaultValues: { new_password: '', new_password_confirm: '' },
  })
  const reset = useMutation({
    mutationFn: (values: Values) =>
      apiSend<undefined>('POST', '/auth/password-reset', {
        token,
        new_password: values.new_password,
      }),
  })
  const { errors } = form.formState
  if (reset.isSuccess) {
    return (
      <PublicLayout title="Đã đặt lại mật khẩu">
        <FormAlert tone="success">Mật khẩu mới đã được lưu. Hãy đăng nhập lại.</FormAlert>
        <Button asChild>
          <Link to="/login">Đăng nhập</Link>
        </Button>
      </PublicLayout>
    )
  }
  return (
    <PublicLayout title="Đặt lại mật khẩu" lead="Chọn một mật khẩu mới, ít nhất 10 ký tự.">
      <form
        noValidate
        className="flex flex-col gap-4"
        onSubmit={form.handleSubmit((values) => reset.mutate(values))}
      >
        {reset.isError && <FormAlert>{errorMessage(reset.error)}</FormAlert>}
        <TextField
          label="Mật khẩu mới"
          placeholder="Ít nhất 10 ký tự"
          autoFocus
          type="password"
          autoComplete="new-password"
          hint="Ít nhất 10 ký tự, không trùng email."
          error={errors.new_password?.message}
          {...form.register('new_password')}
        />
        <TextField
          label="Nhập lại mật khẩu mới"
          placeholder="Gõ lại mật khẩu mới"
          type="password"
          autoComplete="new-password"
          error={errors.new_password_confirm?.message}
          {...form.register('new_password_confirm')}
        />
        <Button type="submit" disabled={reset.isPending}>
          {reset.isPending ? 'Đang lưu…' : 'Đặt lại mật khẩu'}
        </Button>
      </form>
    </PublicLayout>
  )
}
