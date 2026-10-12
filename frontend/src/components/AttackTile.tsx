import type { AttackKind } from '@/contracts/api'
import { ATTACK_EXPLAIN, attackLook } from '@/lib/attack-kinds'
import { cn } from '@/lib/utils'

/**
 * Ô icon của một attack (màu theo nhóm Tấn công / Biến đổi điều kiện / Che khuất). `sm` cho bảng
 * và danh sách, `md` cho thẻ.
 */
export function AttackTile({
  spec,
  size = 'md',
  className,
}: {
  spec: { name: string; kind?: AttackKind | null }
  size?: 'sm' | 'md'
  className?: string
}) {
  const { icon: Icon, tile } = attackLook(spec)
  return (
    <span
      className={cn('tile', size === 'sm' ? 'size-6 rounded-md' : 'size-9', tile, className)}
      aria-hidden="true"
    >
      <Icon className={size === 'sm' ? 'size-3.5' : 'size-[18px]'} />
    </span>
  )
}

/** Tên attack kèm icon nhỏ phía trước (bảng, danh sách). */
export function AttackName({
  name,
  kind,
  children,
  className,
}: {
  name: string
  kind?: AttackKind | null
  /** Chữ hiển thị (mặc định là `name`). */
  children?: React.ReactNode
  className?: string
}) {
  return (
    <span className={cn('inline-flex items-center gap-2 align-middle', className)}>
      <AttackTile spec={{ name, kind }} size="sm" />
      <span className="min-w-0">{children ?? name}</span>
    </span>
  )
}

/** Dòng "Mô phỏng: …": rủi ro ngoài đời mà attack mô phỏng; spec chưa có câu mô tả thì ẩn. */
export function AttackRisk({ name }: { name: string }) {
  const risk = ATTACK_EXPLAIN[name]?.risk
  if (!risk) return null
  return (
    <p className="text-[13px] leading-5">
      <span className="font-medium">Mô phỏng: </span>
      {risk}
    </p>
  )
}
