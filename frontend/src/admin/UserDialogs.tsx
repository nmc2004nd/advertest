import { useState } from 'react'

import { errorMessage } from '@/api/messages'
import { ROLE_LABELS } from '@/auth/roles'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { CopyButton } from '@/components/CopyButton'
import { FormAlert } from '@/components/FormAlert'
import { TextareaField } from '@/components/form/TextField'
import type {
  ApproveRequest,
  PasswordResetLink,
  RejectRequest,
  Role,
  RolesUpdate,
  UserAdminView,
} from '@/contracts/schemas'

import { formatDateTime } from './format'
import { RoleCheckboxes } from './RoleCheckboxes'
import { useAdminMutation } from './useUsers'

interface DialogProps {
  user: UserAdminView
  onClose: () => void
}

function who(user: UserAdminView): string {
  return `${user.full_name} (${user.email})`
}

/** Duyệt: chọn role, chọn sẵn role được yêu cầu; phải có ít nhất một role. */
export function ApproveDialog({ user, onClose }: DialogProps) {
  const [roles, setRoles] = useState<Role[]>(user.requested_role ? [user.requested_role] : [])
  const approve = useAdminMutation<ApproveRequest, UserAdminView>(
    'POST',
    (id) => `/admin/users/${id}/approve`,
  )
  return (
    <ConfirmDialog
      open
      onOpenChange={(open) => !open && onClose()}
      title="Duyệt tài khoản"
      description={who(user)}
      confirmLabel="Duyệt"
      pending={approve.isPending}
      canConfirm={roles.length > 0}
      onConfirm={() => approve.mutate({ userId: user.id, body: { roles } }, { onSuccess: onClose })}
    >
      <RoleCheckboxes legend="Gán vai trò" value={roles} onChange={setRoles} />
      {roles.length === 0 && <p className="text-sm text-destructive">Chọn ít nhất một vai trò.</p>}
      {approve.isError && <FormAlert>{errorMessage(approve.error)}</FormAlert>}
    </ConfirmDialog>
  )
}

/** Từ chối: bắt buộc lý do. */
export function RejectDialog({ user, onClose }: DialogProps) {
  const [reason, setReason] = useState('')
  const reject = useAdminMutation<RejectRequest, UserAdminView>(
    'POST',
    (id) => `/admin/users/${id}/reject`,
  )
  return (
    <ConfirmDialog
      open
      onOpenChange={(open) => !open && onClose()}
      title="Từ chối yêu cầu truy cập"
      description={who(user)}
      confirmLabel="Từ chối"
      destructive
      pending={reject.isPending}
      canConfirm={reason.trim().length > 0}
      onConfirm={() =>
        reject.mutate({ userId: user.id, body: { reason: reason.trim() } }, { onSuccess: onClose })
      }
    >
      <TextareaField
        label="Lý do từ chối (bắt buộc)"
        placeholder="Người dùng sẽ thấy lý do này, ví dụ: email không thuộc tổ chức tham gia dự án."
        value={reason}
        maxLength={2000}
        onChange={(event) => setReason(event.target.value)}
      />
      {reject.isError && <FormAlert>{errorMessage(reject.error)}</FormAlert>}
    </ConfirmDialog>
  )
}

/** Đổi role; bỏ role admin thì cảnh báo và nút xác nhận đổi thành "Bỏ role admin". */
export function RolesDialog({ user, onClose }: DialogProps) {
  const [roles, setRoles] = useState<Role[]>(user.roles)
  const update = useAdminMutation<RolesUpdate, UserAdminView>(
    'PUT',
    (id) => `/admin/users/${id}/roles`,
  )
  const removesAdmin = user.roles.includes('admin') && !roles.includes('admin')
  const unchanged = [...roles].sort().join() === [...user.roles].sort().join()
  return (
    <ConfirmDialog
      open
      onOpenChange={(open) => !open && onClose()}
      title="Đổi vai trò"
      description={who(user)}
      confirmLabel={removesAdmin ? 'Bỏ role admin' : 'Lưu vai trò'}
      destructive={removesAdmin}
      pending={update.isPending}
      canConfirm={roles.length > 0 && !unchanged}
      onConfirm={() => update.mutate({ userId: user.id, body: { roles } }, { onSuccess: onClose })}
    >
      <RoleCheckboxes legend="Vai trò" value={roles} onChange={setRoles} />
      {roles.length === 0 && (
        <p className="text-sm text-destructive">
          Cần ít nhất một vai trò. Muốn chặn truy cập thì vô hiệu hóa tài khoản.
        </p>
      )}
      {removesAdmin && (
        <FormAlert>
          Người này sẽ mất quyền {ROLE_LABELS.admin.toLowerCase()} ngay ở thao tác tiếp theo.
        </FormAlert>
      )}
      {update.isError && <FormAlert>{errorMessage(update.error)}</FormAlert>}
    </ConfirmDialog>
  )
}

export function DisableDialog({ user, onClose }: DialogProps) {
  const disable = useAdminMutation<undefined, UserAdminView>(
    'POST',
    (id) => `/admin/users/${id}/disable`,
  )
  return (
    <ConfirmDialog
      open
      onOpenChange={(open) => !open && onClose()}
      title="Vô hiệu hóa tài khoản"
      description={who(user)}
      confirmLabel="Vô hiệu hóa"
      destructive
      pending={disable.isPending}
      onConfirm={() => disable.mutate({ userId: user.id }, { onSuccess: onClose })}
    >
      <p className="text-sm">
        Người dùng bị đăng xuất khỏi mọi thiết bị ngay lập tức và không đăng nhập được cho tới khi
        được kích hoạt lại.
      </p>
      {disable.isError && <FormAlert>{errorMessage(disable.error)}</FormAlert>}
    </ConfirmDialog>
  )
}

/** Tạo link đặt lại mật khẩu: xác nhận rồi hiện link (chỉ đọc) kèm nút copy. */
export function ResetLinkDialog({ user, onClose }: DialogProps) {
  const create = useAdminMutation<undefined, PasswordResetLink>(
    'POST',
    (id) => `/admin/users/${id}/reset-link`,
  )
  const link = create.data
  return (
    <ConfirmDialog
      open
      onOpenChange={(open) => !open && onClose()}
      title="Link đặt lại mật khẩu"
      description={who(user)}
      confirmLabel={link ? 'Xong' : 'Tạo link'}
      pending={create.isPending}
      onConfirm={() => (link ? onClose() : create.mutate({ userId: user.id }))}
    >
      {link ? (
        <div className="flex flex-col gap-2">
          <label htmlFor="link-dat-lai" className="text-sm font-medium">
            Gửi link này cho người dùng (dùng một lần, hết hạn {formatDateTime(link.expires_at)})
          </label>
          <input
            id="link-dat-lai"
            readOnly
            value={link.url}
            onFocus={(event) => event.target.select()}
            className="min-h-11 w-full rounded-lg border border-input bg-muted px-3 font-mono text-base"
          />
          <CopyButton value={link.url} label="Copy link" targetId="link-dat-lai" />
        </div>
      ) : (
        <p className="text-sm">
          Link cũ chưa dùng của người này sẽ không dùng được nữa. Link mới hết hạn sau 24 giờ.
        </p>
      )}
      {create.isError && <FormAlert>{errorMessage(create.error)}</FormAlert>}
    </ConfirmDialog>
  )
}
