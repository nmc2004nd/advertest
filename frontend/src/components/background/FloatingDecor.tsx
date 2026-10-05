import { useEffect, useRef } from 'react'

import { cn } from '@/lib/utils'

/**
 * Vật trang trí 3D tương tác (tham khảo beehiiv): khối lập phương điểm ảnh, ngôi sao gai, vòng
 * xuyến, lục giác, dấu crash test... Mỗi vật lơ lửng và tự xoay; con trỏ đến gần thì vật né ra,
 * kéo thả được (thả ra thì bật về chỗ cũ như lò xo), bấm vào thì xoay tít. Lớp chứa không chặn
 * chuột, chỉ chính các vật nhận thao tác. `prefers-reduced-motion`: đứng yên, không kéo.
 * Thuần trang trí: aria-hidden, không vào thứ tự Tab.
 */

export type DecorKind = 'cube' | 'star' | 'sparkle' | 'ring' | 'hex' | 'target' | 'pixel'

export interface DecorItem {
  kind: DecorKind
  /** Vị trí gốc, % theo khung chứa. */
  x: number
  y: number
  /** Cạnh (px). */
  size?: number
  /** Độ sâu 0–1: càng gần thì parallax càng mạnh. */
  depth?: number
  /** Màu chủ đạo (một số vật). */
  color?: string
}

interface Body {
  el: HTMLDivElement
  inner: HTMLDivElement
  item: DecorItem
  ox: number
  oy: number
  vx: number
  vy: number
  rx: number
  ry: number
  rz: number
  spin: number
  drag: { px: number; py: number; ox: number; oy: number; moved: boolean } | null
  phase: number
}

export function FloatingDecor({ items, className }: { items: DecorItem[]; className?: string }) {
  const rootRef = useRef<HTMLDivElement>(null)
  const nodes = useRef<(HTMLDivElement | null)[]>([])
  const inners = useRef<(HTMLDivElement | null)[]>([])

  useEffect(() => {
    const root = rootRef.current
    if (!root) return
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const bodies: Body[] = items.flatMap((item, i) => {
      const el = nodes.current[i]
      const inner = inners.current[i]
      if (!el || !inner) return []
      return [
        {
          el,
          inner,
          item,
          ox: 0,
          oy: 0,
          vx: 0,
          vy: 0,
          rx: item.kind === 'ring' ? 62 : -18 + i * 9,
          ry: 20 + i * 37,
          rz: i * 23,
          spin: 0,
          drag: null,
          phase: i * 1.7,
        },
      ]
    })
    const pointer = { x: -1e4, y: -1e4, nx: 0, ny: 0 }
    let raf = 0

    const place = (b: Body) => {
      b.el.style.transform = `translate3d(${b.ox.toFixed(1)}px, ${b.oy.toFixed(1)}px, 0)`
      const cube = b.item.kind === 'cube' || b.item.kind === 'pixel'
      // Khối lập phương xoay đủ vòng; vật phẳng chỉ lắc quanh trục Y (±40°) để không bao giờ
      // quay cạnh mỏng ra trước, và quay tròn trong mặt phẳng.
      const wobble = Math.sin((b.ry * Math.PI) / 180) * 40
      b.inner.style.transform = cube
        ? `rotateX(${b.rx.toFixed(1)}deg) rotateY(${b.ry.toFixed(1)}deg) rotateZ(${b.rz.toFixed(1)}deg)`
        : b.item.kind === 'ring'
          ? `rotateX(${(55 + wobble * 0.3).toFixed(1)}deg) rotateY(${wobble.toFixed(1)}deg) rotateZ(${b.rz.toFixed(1)}deg)`
          : `rotateY(${wobble.toFixed(1)}deg) rotateZ(${(b.rz * 0.5).toFixed(1)}deg)`
    }
    bodies.forEach(place)
    if (reduce) return

    const onMove = (e: PointerEvent) => {
      const r = root.getBoundingClientRect()
      pointer.x = e.clientX - r.left
      pointer.y = e.clientY - r.top
      pointer.nx = (pointer.x / r.width - 0.5) * 2
      pointer.ny = (pointer.y / r.height - 0.5) * 2
      for (const b of bodies) {
        if (!b.drag) continue
        const dx = e.clientX - b.drag.px
        const dy = e.clientY - b.drag.py
        if (Math.hypot(dx, dy) > 4) b.drag.moved = true
        const nx = b.drag.ox + dx
        const ny = b.drag.oy + dy
        b.vx = nx - b.ox
        b.vy = ny - b.oy
        b.ox = nx
        b.oy = ny
      }
    }
    const onUp = () => {
      for (const b of bodies) {
        if (!b.drag) continue
        if (!b.drag.moved) b.spin += 26 // bấm (không kéo): xoay tít
        b.drag = null
        b.el.classList.remove('is-dragging')
      }
    }
    const downs = bodies.map((b) => {
      const onDown = (e: PointerEvent) => {
        e.preventDefault()
        b.drag = { px: e.clientX, py: e.clientY, ox: b.ox, oy: b.oy, moved: false }
        b.el.classList.add('is-dragging')
      }
      b.el.addEventListener('pointerdown', onDown)
      return () => b.el.removeEventListener('pointerdown', onDown)
    })

    const tick = (now: number) => {
      const r = root.getBoundingClientRect()
      for (const b of bodies) {
        const depth = b.item.depth ?? 0.5
        if (!b.drag) {
          // Đích: lơ lửng nhẹ + parallax theo con trỏ.
          const tx = -pointer.nx * 26 * depth + Math.sin(now / 1400 + b.phase) * 6
          const ty = -pointer.ny * 20 * depth + Math.cos(now / 1700 + b.phase) * 9
          b.vx += (tx - b.ox) * 0.03
          b.vy += (ty - b.oy) * 0.03
          // Né con trỏ khi nó đến gần.
          const cx = (b.item.x / 100) * r.width + b.ox
          const cy = (b.item.y / 100) * r.height + b.oy
          const dx = cx - pointer.x
          const dy = cy - pointer.y
          const dist = Math.hypot(dx, dy)
          const reach = (b.item.size ?? 56) * 1.6
          if (dist < reach && dist > 0.1) {
            const push = (1 - dist / reach) * 2.2
            b.vx += (dx / dist) * push
            b.vy += (dy / dist) * push
          }
          b.vx *= 0.86
          b.vy *= 0.86
          b.ox += b.vx
          b.oy += b.vy
        }
        const speed = Math.hypot(b.vx, b.vy)
        b.spin *= 0.95
        b.ry += 0.35 + speed * 0.6 + b.spin
        b.rx += b.item.kind === 'ring' ? 0 : 0.18 + b.spin * 0.4
        b.rz += 0.12 + b.vx * 0.3
        place(b)
      }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    window.addEventListener('pointermove', onMove, { passive: true })
    window.addEventListener('pointerup', onUp)
    window.addEventListener('pointercancel', onUp)
    return () => {
      cancelAnimationFrame(raf)
      downs.forEach((off) => off())
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
      window.removeEventListener('pointercancel', onUp)
    }
  }, [items])

  return (
    <div
      ref={rootRef}
      aria-hidden
      className={cn('decor pointer-events-none absolute inset-0 overflow-hidden', className)}
    >
      {items.map((item, i) => {
        const size = item.size ?? 56
        return (
          <div
            key={i}
            ref={(el) => {
              nodes.current[i] = el
            }}
            className="decor-item"
            style={{
              left: `${item.x}%`,
              top: `${item.y}%`,
              width: size,
              height: size,
              marginLeft: -size / 2,
              marginTop: -size / 2,
            }}
          >
            <div
              ref={(el) => {
                inners.current[i] = el
              }}
              className="decor-inner"
            >
              <Shape item={item} size={size} />
            </div>
          </div>
        )
      })}
    </div>
  )
}

const INK = '#0f172a'

function Shape({ item, size }: { item: DecorItem; size: number }) {
  switch (item.kind) {
    case 'cube':
    case 'pixel': {
      const colors =
        item.kind === 'pixel'
          ? ['#ffffff', '#fbcfe8', '#ddd6fe', '#ffffff', '#bfdbfe', '#fbcfe8']
          : ['#f9a8d4', '#c4b5fd', '#93c5fd', '#f9a8d4', '#c4b5fd', '#fde68a']
      const h = size / 2
      const faces = [
        `rotateY(0deg) translateZ(${h}px)`,
        `rotateY(90deg) translateZ(${h}px)`,
        `rotateY(180deg) translateZ(${h}px)`,
        `rotateY(-90deg) translateZ(${h}px)`,
        `rotateX(90deg) translateZ(${h}px)`,
        `rotateX(-90deg) translateZ(${h}px)`,
      ]
      return (
        <div className="decor-3d" style={{ width: size, height: size }}>
          {faces.map((t, i) => (
            <span
              key={i}
              className="decor-face"
              style={{ transform: t, background: colors[i], borderRadius: size * 0.12 }}
            >
              {item.kind === 'cube' && i % 2 === 0 && (
                <span className="decor-grid" style={{ borderRadius: size * 0.08 }} />
              )}
            </span>
          ))}
        </div>
      )
    }
    case 'ring':
      return (
        <div
          className="size-full rounded-full"
          style={{
            border: `${Math.round(size * 0.16)}px solid transparent`,
            background:
              'linear-gradient(#0000,#0000) padding-box, linear-gradient(135deg,#60a5fa,#a78bfa,#f472b6) border-box',
            boxShadow: `0 0 0 2px ${INK}, inset 0 0 0 2px ${INK}`,
          }}
        />
      )
    case 'star': {
      const pts = Array.from({ length: 24 }, (_, i) => {
        const r = i % 2 === 0 ? 48 : 30
        const a = (i / 24) * Math.PI * 2
        return `${(50 + Math.cos(a) * r).toFixed(1)},${(50 + Math.sin(a) * r).toFixed(1)}`
      }).join(' ')
      return (
        <svg viewBox="0 0 100 100" className="size-full overflow-visible">
          <polygon
            points={pts}
            fill={item.color ?? '#fde68a'}
            stroke={INK}
            strokeWidth="3.5"
            strokeLinejoin="round"
          />
        </svg>
      )
    }
    case 'sparkle':
      return (
        <svg viewBox="0 0 24 24" className="size-full overflow-visible">
          <path
            d="M12 1C13 8 16 11 23 12 16 13 13 16 12 23 11 16 8 13 1 12 8 11 11 8 12 1Z"
            fill={item.color ?? '#ffffff'}
            stroke={INK}
            strokeWidth="1.3"
            strokeLinejoin="round"
          />
        </svg>
      )
    case 'hex':
      return (
        <svg viewBox="0 0 100 100" className="size-full overflow-visible">
          <path d="M56 8l38 22v44L56 96 18 74V30z" fill={INK} />
          <path
            d="M50 4l38 22v44L50 92 12 70V26z"
            fill={item.color ?? '#ddd6fe'}
            stroke={INK}
            strokeWidth="3.5"
            strokeLinejoin="round"
          />
          <path
            d="M34 40v-8h8M58 32h8v8M66 56v8h-8M42 64h-8v-8"
            fill="none"
            stroke={INK}
            strokeWidth="4"
            strokeLinecap="round"
          />
        </svg>
      )
    case 'target':
      return (
        <svg viewBox="0 0 100 100" className="size-full overflow-visible">
          <circle cx="50" cy="50" r="46" fill="#fff" stroke={INK} strokeWidth="4" />
          <path d="M50 50V4A46 46 0 0 1 96 50z" fill={item.color ?? '#7c3aed'} />
          <path d="M50 50V96A46 46 0 0 1 4 50z" fill={item.color ?? '#7c3aed'} />
          <circle cx="50" cy="50" r="46" fill="none" stroke={INK} strokeWidth="4" />
        </svg>
      )
  }
}
