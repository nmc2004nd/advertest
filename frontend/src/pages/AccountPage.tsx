import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router'
import type { z } from 'zod'

import { apiSend, ApiError } from '@/api/client'
import { errorMessage } from '@/api/messages'
import { ROLE_LABELS } from '@/auth/roles'
import { passwordChangeSchema } from '@/auth/schemas'
import { useMe } from '@/auth/useMe'
import { FormAlert } from '@/components/FormAlert'
import { TextField } from '@/components/form/TextField'
import { useZodForm } from '@/components/form/useZodForm'
import { Button } from '@/components/ui/button'

type PasswordValues = z.output<typeof passwordChangeSchema>

export function AccountPage() {
  const { data: me } = useMe()
  if (!me) return null
  return (
    <div className="mx-auto flex max-w-xl flex-col gap-8 p-4 md:p-6">
      <h1 className="text-2xl font-semibold">Tài khoản</h1>
      <section className="flex flex-col gap-2" aria-labelledby="thong-tin">
        <h2 id="thong-tin" className="text-lg font-semibold">
          Thông tin
        </h2>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
          <dt className="text-muted-foreground">Họ tên</dt>
          <dd>{me.full_name}</dd>
          <dt className="text-muted-foreground">Email</dt>
          <dd className="break-all">{me.email}</dd>
          <dt className="text-muted-foreground">Vai trò</dt>
          <dd>{me.roles.map((role) => ROLE_LABELS[role]).join(', ') || 'Chưa có'}</dd>
        </dl>
      </section>
      <ChangePassword />
      <Logout />
    </div>
  )
}

function ChangePassword() {
  const form = useZodForm(passwordChangeSchema, {
    defaultValues: { current_password: '', new_password: '', new_password_confirm: '' },
  })
  const change = useMutation({
    mutationFn: (values: PasswordValues) =>
      apiSend<undefined>('POST', '/auth/password', {
        current_password: values.current_password,
        new_password: values.new_password,
      }),
    onSuccess: () => form.reset(),
    onError: (error) => {
      // Sai mật khẩu hiện tại: 422 invalid_request (không phải 401), báo ngay dưới ô đó.
      if (error instanceof ApiError && error.code === 'invalid_request') {
        form.setError('current_password', { message: error.message })
      }
    },
  })
  const { errors } = form.formState
  const formError =
    change.isError && !(change.error instanceof ApiError && change.error.code === 'invalid_request')
  return (
    <section className="flex flex-col gap-4" aria-labelledby="doi-mat-khau">
      <h2 id="doi-mat-khau" className="text-lg font-semibold">
        Đổi mật khẩu
      </h2>
      <form
        noValidate
        className="flex flex-col gap-4"
        onSubmit={form.handleSubmit((values) => change.mutate(values))}
      >
        {change.isSuccess && (
          <FormAlert tone="success">
            Đã đổi mật khẩu. Các phiên đăng nhập khác của bạn đã bị đăng xuất.
          </FormAlert>
        )}
        {formError && <FormAlert>{errorMessage(change.error)}</FormAlert>}
        <TextField
          label="Mật khẩu hiện tại"
          type="password"
          autoComplete="current-password"
          error={errors.current_password?.message}
          {...form.register('current_password')}
        />
        <TextField
          label="Mật khẩu mới"
          type="password"
          autoComplete="new-password"
          hint="Ít nhất 10 ký tự, không trùng email."
          error={errors.new_password?.message}
          {...form.register('new_password')}
        />
        <TextField
          label="Nhập lại mật khẩu mới"
          type="password"
          autoComplete="new-password"
          error={errors.new_password_confirm?.message}
          {...form.register('new_password_confirm')}
        />
        <Button type="submit" className="self-start" disabled={change.isPending}>
          {change.isPending ? 'Đang lưu…' : 'Đổi mật khẩu'}
        </Button>
      </form>
    </section>
  )
}

function Logout() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const logout = useMutation({
    mutationFn: () => apiSend<undefined>('POST', '/auth/logout'),
    onSettled: () => {
      // Kể cả khi phiên đã hết hạn: xóa dữ liệu của người dùng khỏi bộ nhớ và về trang đăng nhập.
      queryClient.clear()
      void navigate('/login', { replace: true })
    },
  })
  return (
    <section className="border-t border-border pt-6">
      <Button variant="outline" disabled={logout.isPending} onClick={() => logout.mutate()}>
        {logout.isPending ? 'Đang đăng xuất…' : 'Đăng xuất'}
      </Button>
    </section>
  )
}
