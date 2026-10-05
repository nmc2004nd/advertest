import { useMutation, useQueryClient } from '@tanstack/react-query'
import { FlaskConical, LogOut, ShieldCheck, Users } from 'lucide-react'
import { useNavigate } from 'react-router'
import type { z } from 'zod'

import { apiSend, ApiError } from '@/api/client'
import { errorMessage } from '@/api/messages'
import { ROLE_LABELS } from '@/auth/roles'
import { passwordChangeSchema } from '@/auth/schemas'
import { useMe } from '@/auth/useMe'
import { Avatar } from '@/components/Avatar'
import { FormAlert } from '@/components/FormAlert'
import { TextField } from '@/components/form/TextField'
import { useZodForm } from '@/components/form/useZodForm'
import { Button } from '@/components/ui/button'
import type { Role } from '@/contracts/schemas'
import { PlaneArt } from '@/layout/hero-art'

type PasswordValues = z.output<typeof passwordChangeSchema>

/** Việc mỗi vai trò làm được, nói bằng lời của người dùng. */
const ROLE_CAN: Record<Role, { icon: typeof FlaskConical; text: string }> = {
  engineer: { icon: FlaskConical, text: 'Tạo và chạy experiment, gửi kết quả cho reviewer.' },
  reviewer: {
    icon: ShieldCheck,
    text: 'Chốt protocol, review case, quyết định và tải report chính thức.',
  },
  admin: { icon: Users, text: 'Duyệt tài khoản, quản lý attack catalog và xem audit log.' },
}

/**
 * Tài khoản kiểu chia đôi (tham khảo beehiiv): thẻ tối bên trái là hồ sơ và nút đăng xuất, thẻ
 * trắng bên phải là quyền của bạn và đổi mật khẩu.
 */
export function AccountPage() {
  const { data: me } = useMe()
  if (!me) return null
  return (
    <div className="mx-auto grid max-w-6xl items-start gap-5 p-4 md:p-8 lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)]">
      <section
        aria-labelledby="thong-tin"
        className="relative isolate flex min-h-[460px] flex-col gap-6 overflow-hidden rounded-[20px] bg-[#1e293b] p-7 text-white md:p-9 lg:sticky lg:top-8"
      >
        <div aria-hidden className="account-hex absolute inset-0 -z-10" />
        <PlaneArt className="absolute right-6 bottom-24 -z-10 w-48 opacity-90" />
        <h1 className="text-[15px] font-semibold text-white/70">Tài khoản</h1>
        <div className="flex items-center gap-4">
          <Avatar name={me.full_name} size={64} />
          <div className="min-w-0">
            <h2
              id="thong-tin"
              className="text-[26px] leading-tight font-bold tracking-[-0.03em] break-words"
            >
              {me.full_name}
            </h2>
            <p className="mt-1 text-[14.5px] break-all text-white/75">{me.email}</p>
          </div>
        </div>
        <dl className="sr-only">
          <dt>Họ tên</dt>
          <dd>{me.full_name}</dd>
          <dt>Email</dt>
          <dd>{me.email}</dd>
          <dt>Vai trò</dt>
          <dd>{me.roles.map((role) => ROLE_LABELS[role]).join(', ') || 'Chưa có'}</dd>
        </dl>
        <ul className="flex flex-wrap gap-2" aria-hidden>
          {me.roles.length === 0 ? (
            <li className="rounded-full bg-white/10 px-3 py-1 text-[13px]">Chưa có vai trò</li>
          ) : (
            me.roles.map((role) => (
              <li
                key={role}
                className="rounded-full bg-white/12 px-3 py-1 text-[13px] font-semibold"
              >
                {ROLE_LABELS[role]}
              </li>
            ))
          )}
        </ul>
        <div className="mt-auto">
          <Logout />
        </div>
      </section>
      <div className="panel flex flex-col gap-8 p-6 md:p-9">
        <section aria-labelledby="quyen" className="flex flex-col gap-4">
          <h2 id="quyen" className="text-[22px] font-bold tracking-[-0.025em]">
            Bạn làm được gì ở đây
          </h2>
          {me.roles.length === 0 ? (
            <p className="text-muted-foreground">
              Tài khoản chưa có vai trò nào. Hãy nhắn quản trị viên để được cấp quyền.
            </p>
          ) : (
            <ul className="flex flex-col gap-4">
              {me.roles.map((role) => {
                const item = ROLE_CAN[role]
                return (
                  <li key={role} className="flex items-start gap-3">
                    <span
                      className="tile size-9 [--tile-bg:var(--pink-soft)] [--tile-fg:var(--pink)]"
                      aria-hidden
                    >
                      <item.icon className="size-[18px]" />
                    </span>
                    <span className="flex flex-col">
                      <span className="text-[15px] font-semibold">{ROLE_LABELS[role]}</span>
                      <span className="text-[14px] leading-6 text-muted-foreground">
                        {item.text}
                      </span>
                    </span>
                  </li>
                )
              })}
            </ul>
          )}
        </section>
        <div className="border-t border-line" />
        <ChangePassword />
      </div>
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
      <div className="flex flex-col gap-1">
        <h2 id="doi-mat-khau" className="text-[22px] font-bold tracking-[-0.025em]">
          Đổi mật khẩu
        </h2>
        <p className="text-[14px] text-muted-foreground">
          Đổi xong, các phiên đăng nhập khác của bạn sẽ bị đăng xuất.
        </p>
      </div>
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
          placeholder="Mật khẩu đang dùng"
          type="password"
          autoComplete="current-password"
          error={errors.current_password?.message}
          {...form.register('current_password')}
        />
        <TextField
          label="Mật khẩu mới"
          placeholder="Ít nhất 10 ký tự"
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
    <Button
      variant="outline"
      className="border-white/30 bg-transparent text-white hover:bg-white/10 hover:text-white"
      disabled={logout.isPending}
      onClick={() => logout.mutate()}
    >
      <LogOut aria-hidden />
      {logout.isPending ? 'Đang đăng xuất…' : 'Đăng xuất'}
    </Button>
  )
}
