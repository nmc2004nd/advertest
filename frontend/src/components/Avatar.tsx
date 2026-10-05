import { initials } from '@/lib/initials'
import { cn } from '@/lib/utils'

// Bảng màu ấm, đủ tương phản với chữ trắng (≥ 4.5:1); mỗi người luôn cùng một màu.
const COLORS = [
  '#7a4e2d',
  '#2f6b5a',
  '#5b4a8a',
  '#8a3b52',
  '#3d5f86',
  '#6b5d24',
  '#8a4a2b',
  '#40665f',
]

function hash(text: string): number {
  let h = 0
  for (const ch of text) h = (h * 31 + ch.charCodeAt(0)) >>> 0
  return h
}

/** Avatar chữ cái đầu: giúp nhận ra ai đang làm gì ở mọi chỗ chuyển giao việc. */
export function Avatar({
  name,
  size = 28,
  className,
}: {
  name?: string | null
  size?: number
  className?: string
}) {
  return (
    <span
      aria-hidden
      className={cn('avatar', className)}
      style={
        {
          width: size,
          height: size,
          fontSize: Math.round(size * 0.38),
          '--avatar': COLORS[hash(name ?? '') % COLORS.length],
        } as React.CSSProperties
      }
    >
      {initials(name)}
    </span>
  )
}

/** Tên người kèm avatar, dùng trong câu ("Minh Trần đã gửi duyệt"). */
export function Person({ name, size = 22 }: { name: string; size?: number }) {
  return (
    <span className="inline-flex items-center gap-1.5 align-middle font-medium text-foreground">
      <Avatar name={name} size={size} />
      {name}
    </span>
  )
}
