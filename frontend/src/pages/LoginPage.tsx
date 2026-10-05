import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useSearchParams } from 'react-router'

import { safeNext } from '@/api/auth-redirect'
import { isAccountStatusCode } from '@/auth/account-status'
import { apiSend, ApiError } from '@/api/client'
import { errorMessage } from '@/api/messages'
import { loginSchema } from '@/auth/schemas'
import { ME_QUERY_KEY } from '@/auth/useMe'
import { FormAlert } from '@/components/FormAlert'
import { TextField } from '@/components/form/TextField'
import { useZodForm } from '@/components/form/useZodForm'
import { Button } from '@/components/ui/button'
import type { LoginRequest, Me } from '@/contracts/schemas'
import { PublicLayout } from '@/layout/PublicLayout'

export function LoginPage() {
  const [params] = useSearchParams()
  const next = safeNext(params.get('next'))
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const form = useZodForm(loginSchema, { defaultValues: { email: '', password: '' } })
  const login = useMutation({
    mutationFn: (body: LoginRequest) => apiSend<Me>('POST', '/auth/login', body),
    onSuccess: (me) => {
      queryClient.setQueryData(ME_QUERY_KEY, me)
      void navigate(next, { replace: true })
    },
    onError: (error) => {
      if (error instanceof ApiError && isAccountStatusCode(error.code)) {
        void navigate(`/pending?code=${error.code}`)
      }
    },
  })
  const { errors } = form.formState
  const showError =
    login.isError && !(login.error instanceof ApiError && isAccountStatusCode(login.error.code))
  return (
    <PublicLayout
      title="Đăng nhập"
      lead="Chào mừng trở lại 👋 Tiếp tục kiểm định model của nhóm bạn."
    >
      <form
        noValidate
        className="flex flex-col gap-4"
        onSubmit={form.handleSubmit((values) => login.mutate(values))}
      >
        {showError && <FormAlert>{errorMessage(login.error)}</FormAlert>}
        <TextField
          label="Email"
          type="email"
          placeholder="ten@congty.vn"
          autoFocus
          autoComplete="email"
          inputMode="email"
          error={errors.email?.message}
          {...form.register('email')}
        />
        <TextField
          label="Mật khẩu"
          type="password"
          placeholder="Mật khẩu của bạn"
          hint="Quên mật khẩu: nhờ quản trị viên tạo link đặt lại."
          autoComplete="current-password"
          error={errors.password?.message}
          {...form.register('password')}
        />
        <Button type="submit" size="lg" disabled={login.isPending}>
          {login.isPending ? 'Đang đăng nhập…' : 'Đăng nhập'}
        </Button>
      </form>
      <p className="text-sm text-muted-foreground">
        Chưa có tài khoản?{' '}
        <Link
          to="/request-access"
          className="font-semibold text-foreground underline underline-offset-4 hover:text-violet"
        >
          Yêu cầu truy cập
        </Link>
      </p>
    </PublicLayout>
  )
}
