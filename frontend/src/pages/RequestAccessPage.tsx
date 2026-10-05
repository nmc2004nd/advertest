import { useMutation } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router'
import type { z } from 'zod'

import { apiSend } from '@/api/client'
import { errorMessage } from '@/api/messages'
import { ROLE_LABELS } from '@/auth/roles'
import { accessRequestSchema } from '@/auth/schemas'
import { FormAlert } from '@/components/FormAlert'
import { SelectField, TextareaField, TextField } from '@/components/form/TextField'
import { useZodForm } from '@/components/form/useZodForm'
import { Button } from '@/components/ui/button'
import { roleValues, type AccessRequest } from '@/contracts/schemas'
import { PublicLayout } from '@/layout/PublicLayout'

type Values = z.output<typeof accessRequestSchema>

function toBody(values: Values): AccessRequest {
  return {
    full_name: values.full_name,
    email: values.email,
    organization: values.organization || null,
    requested_role: values.requested_role,
    reason: values.reason,
    password: values.password,
  }
}

export function RequestAccessPage() {
  const navigate = useNavigate()
  const form = useZodForm(accessRequestSchema, {
    defaultValues: {
      full_name: '',
      email: '',
      organization: '',
      requested_role: 'engineer',
      reason: '',
      password: '',
      password_confirm: '',
    },
  })
  const submit = useMutation({
    mutationFn: (values: Values) =>
      apiSend<undefined>('POST', '/auth/request-access', toBody(values)),
    onSuccess: () => void navigate('/request-access/sent', { replace: true }),
  })
  const { errors } = form.formState
  return (
    <PublicLayout
      title="Yêu cầu truy cập"
      lead="Điền vài thông tin, quản trị viên sẽ duyệt và báo cho bạn qua email."
    >
      <p className="text-muted-foreground">
        Quản trị viên sẽ duyệt yêu cầu và gán vai trò trước khi bạn đăng nhập được.
      </p>
      <form
        noValidate
        className="flex flex-col gap-4"
        onSubmit={form.handleSubmit((values) => submit.mutate(values))}
      >
        {submit.isError && <FormAlert>{errorMessage(submit.error)}</FormAlert>}
        <TextField
          label="Họ tên"
          placeholder="Nguyễn Văn An"
          autoFocus
          autoComplete="name"
          error={errors.full_name?.message}
          {...form.register('full_name')}
        />
        <TextField
          label="Email"
          type="email"
          placeholder="ten@congty.vn"
          hint="Dùng email công việc: đây là tên đăng nhập của bạn."
          autoComplete="email"
          inputMode="email"
          error={errors.email?.message}
          {...form.register('email')}
        />
        <TextField
          label="Tổ chức (không bắt buộc)"
          placeholder="Ví dụ: Phòng thí nghiệm xe tự hành"
          autoComplete="organization"
          error={errors.organization?.message}
          {...form.register('organization')}
        />
        <SelectField
          label="Vai trò đề nghị"
          hint="Kỹ sư chạy experiment; reviewer duyệt kết quả và xuất report."
          error={errors.requested_role?.message}
          {...form.register('requested_role')}
        >
          {roleValues.map((role) => (
            <option key={role} value={role}>
              {ROLE_LABELS[role]}
            </option>
          ))}
        </SelectField>
        <TextareaField
          label="Lý do cần truy cập"
          placeholder="Ví dụ: kiểm định YOLOv8 cho dự án robot giao hàng trước đợt thử nghiệm tháng 11"
          error={errors.reason?.message}
          {...form.register('reason')}
        />
        <TextField
          label="Mật khẩu"
          type="password"
          autoComplete="new-password"
          placeholder="Ít nhất 10 ký tự"
          hint="Ít nhất 10 ký tự, không trùng email."
          error={errors.password?.message}
          {...form.register('password')}
        />
        <TextField
          label="Nhập lại mật khẩu"
          placeholder="Gõ lại mật khẩu ở trên"
          type="password"
          autoComplete="new-password"
          error={errors.password_confirm?.message}
          {...form.register('password_confirm')}
        />
        <Button type="submit" size="lg" disabled={submit.isPending}>
          {submit.isPending ? 'Đang gửi…' : 'Gửi yêu cầu'}
        </Button>
      </form>
      <p className="text-sm text-muted-foreground">
        Đã có tài khoản?{' '}
        <Link
          to="/login"
          className="font-semibold text-foreground underline underline-offset-4 hover:text-violet"
        >
          Đăng nhập
        </Link>
      </p>
    </PublicLayout>
  )
}

/** Màn hình xác nhận: nội dung giống nhau dù email đã tồn tại hay chưa (không lộ tài khoản). */
export function RequestAccessSentPage() {
  return (
    <PublicLayout title="Đã gửi yêu cầu">
      <FormAlert tone="success">
        Yêu cầu truy cập đã được ghi nhận. Quản trị viên sẽ xem xét và gán vai trò cho bạn.
      </FormAlert>
      <p className="text-muted-foreground">
        Bạn có thể thử đăng nhập sau: nếu yêu cầu chưa được duyệt, hệ thống sẽ cho biết trạng thái.
      </p>
      <Button asChild variant="outline">
        <Link to="/login">Đến trang đăng nhập</Link>
      </Button>
    </PublicLayout>
  )
}
