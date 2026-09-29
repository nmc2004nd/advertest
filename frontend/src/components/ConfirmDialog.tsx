import type { ReactNode } from 'react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from '@/components/ui/dialog'

interface ConfirmDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description?: string
  /** Tóm tắt điều sắp xảy ra, hoặc ô nhập bổ sung (ví dụ lý do từ chối). */
  children?: ReactNode
  confirmLabel: string
  destructive?: boolean
  pending?: boolean
  /** Có thể xác nhận chưa (ví dụ đã nhập lý do). */
  canConfirm?: boolean
  onConfirm: () => void
}

/**
 * Hộp xác nhận cho thao tác cần cân nhắc: dialog trên desktop, bottom sheet trên điện thoại.
 * Nút xếp dọc, rộng hết khung trên điện thoại để dễ chạm.
 */
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  children,
  confirmLabel,
  destructive = false,
  pending = false,
  canConfirm = true,
  onConfirm,
}: ConfirmDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogTitle>{title}</DialogTitle>
        {description ? (
          <DialogDescription>{description}</DialogDescription>
        ) : (
          <DialogDescription className="sr-only">{title}</DialogDescription>
        )}
        {children}
        <div className="flex flex-col-reverse gap-2 md:flex-row md:justify-end">
          <DialogClose asChild>
            <Button variant="outline" disabled={pending}>
              Hủy
            </Button>
          </DialogClose>
          <Button
            variant={destructive ? 'destructive' : 'default'}
            disabled={pending || !canConfirm}
            onClick={onConfirm}
          >
            {pending ? 'Đang xử lý…' : confirmLabel}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
