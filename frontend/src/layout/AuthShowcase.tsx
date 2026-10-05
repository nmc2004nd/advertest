import { useEffect, useRef, useState } from 'react'

/**
 * Nửa phải của trang đăng nhập, nằm trên nền sóng của cả trang: ở giữa là một tấm thẻ minh họa viền mực
 * (phong cách beehiiv) kể đúng việc AdverTest làm: cùng một bức ảnh, model nhận ra ô tô; thêm nhiễu
 * thì bỏ sót; reviewer xác nhận. Thẻ nghiêng 3D theo con trỏ, các nhãn nổi trôi nhẹ. Thuần trang trí
 * (aria-hidden), không có gì bấm được.
 */
export function AuthShowcase() {
  const stageRef = useRef<HTMLDivElement>(null)
  const cardRef = useRef<HTMLDivElement>(null)
  const [attacked, setAttacked] = useState(false)

  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const id = window.setInterval(() => setAttacked((v) => !v), 2800)
    const stage = stageRef.current
    const card = cardRef.current
    if (!stage || !card) return () => window.clearInterval(id)
    const onMove = (event: PointerEvent) => {
      const rect = stage.getBoundingClientRect()
      const x = (event.clientX - rect.left) / rect.width - 0.5
      const y = (event.clientY - rect.top) / rect.height - 0.5
      card.style.setProperty('--ry', `${(x * 14).toFixed(2)}deg`)
      card.style.setProperty('--rx', `${(-y * 12).toFixed(2)}deg`)
    }
    const onLeave = () => {
      card.style.setProperty('--ry', '-6deg')
      card.style.setProperty('--rx', '4deg')
    }
    onLeave()
    stage.addEventListener('pointermove', onMove)
    stage.addEventListener('pointerleave', onLeave)
    return () => {
      window.clearInterval(id)
      stage.removeEventListener('pointermove', onMove)
      stage.removeEventListener('pointerleave', onLeave)
    }
  }, [])

  return (
    <div
      ref={stageRef}
      aria-hidden
      className="relative flex h-full min-h-[640px] flex-col items-center justify-center"
    >
      <div className="relative z-10 flex w-full max-w-[460px] flex-col items-center gap-10 px-6">
        <div ref={cardRef} className="tilt relative w-full">
          <Starburst className="spin-slow pop absolute -top-9 -right-8 size-20 [--z:70px]" />
          <Sparkle className="twinkle pop absolute -top-5 left-6 size-6 [--z:60px]" />
          <Sparkle className="twinkle pop absolute -bottom-6 -left-7 size-8 [animation-delay:1.2s] [--z:60px]" />

          <div className="ink-card relative overflow-hidden p-4">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <span className="flex size-8 items-center justify-center rounded-lg border-2 border-[#0f172a] bg-[#fde68a] text-[13px] font-black">
                  AT
                </span>
                <div className="leading-tight">
                  <p className="text-[13px] font-bold">Ảnh #0412 · đường đêm</p>
                  <p className="text-[11.5px] text-[#475569]">YOLOv8n · ngưỡng 0.25</p>
                </div>
              </div>
              <Toggle on={attacked} />
            </div>

            <div className="relative mt-3 overflow-hidden rounded-xl border-2 border-[#0f172a]">
              <RoadScene attacked={attacked} />
            </div>

            <div className="mt-4 flex items-center gap-2">
              <Step done label="Chọn ảnh" />
              <Connector />
              <Step done label="Tấn công" />
              <Connector />
              <Step done={!attacked} label="Đo" />
              <Connector />
              <span className="flex size-9 items-center justify-center rounded-full border-2 border-[#0f172a] bg-[#ec4899] text-white shadow-[2px_2px_0_#0f172a]">
                <svg
                  viewBox="0 0 24 24"
                  className="size-[18px]"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.4"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M12 3l7 3v5c0 4.5-3 8.3-7 10-4-1.7-7-5.5-7-10V6z" />
                  <path d="M9 12l2 2 4-4" />
                </svg>
              </span>
            </div>
          </div>

          <div className="ink-chip float pop absolute -top-5 -left-10 flex items-center gap-1.5 px-3 py-1.5 text-[12.5px] font-bold [--z:90px]">
            <span className="size-2 rounded-full bg-[#dc2626]" />
            mAP giảm 0.21
          </div>
          <div className="ink-chip float-slow pop absolute -right-9 -bottom-5 flex items-center gap-1.5 bg-[#bbf7d0] px-3 py-1.5 text-[12.5px] font-bold [--z:90px]">
            ✓ Reviewer đã duyệt
          </div>
        </div>

        <div className="flex w-full flex-col items-center gap-3 rounded-[22px] bg-white/60 px-6 py-5 text-center text-[#1e293b] backdrop-blur-md">
          <p className="text-[clamp(1.4rem,1.9vw,1.85rem)] leading-[1.15] font-bold tracking-[-0.03em] ">
            Biết model sẽ gãy ở đâu,
            <br />
            <span className="relative inline-block">
              trước khi nó lên đường.
              <svg
                viewBox="0 0 300 18"
                className="absolute -bottom-3 left-0 h-3 w-full"
                fill="none"
              >
                <path
                  className="draw"
                  d="M4 12 C 60 2, 120 16, 180 8 S 270 6, 296 10"
                  stroke="#ec4899"
                  strokeWidth="4"
                  strokeLinecap="round"
                />
              </svg>
            </span>
          </p>
          <p className="max-w-sm text-[14.5px] leading-6 text-[#334155]">
            Thử model nhận diện với nhiễu, thời tiết xấu và vật che khuất, rồi để một người độc lập
            kết luận.
          </p>
        </div>
      </div>
    </div>
  )
}

function Toggle({ on }: { on: boolean }) {
  return (
    <span className="flex items-center gap-2 text-[11.5px] font-bold">
      <span className={on ? 'text-[#475569]' : ''}>Gốc</span>
      <span
        className={`relative h-6 w-11 rounded-full border-2 border-[#0f172a] transition-colors duration-300 ${on ? 'bg-[#ec4899]' : 'bg-[#e2e8f0]'}`}
      >
        <span
          className={`absolute top-0.5 size-4 rounded-full border-2 border-[#0f172a] bg-white transition-[left] duration-300 ${on ? 'left-[22px]' : 'left-0.5'}`}
        />
      </span>
      <span className={on ? '' : 'text-[#475569]'}>Nhiễu</span>
    </span>
  )
}

function Step({ done, label }: { done: boolean; label: string }) {
  return (
    <span className="flex flex-col items-center gap-1">
      <span
        className={`flex size-7 items-center justify-center rounded-full border-2 border-[#0f172a] text-[12px] font-black transition-colors duration-300 ${done ? 'bg-[#0f172a] text-white' : 'bg-white text-[#0f172a]'}`}
      >
        {done ? '✓' : '…'}
      </span>
      <span className="text-[10.5px] font-semibold text-[#475569]">{label}</span>
    </span>
  )
}

function Connector() {
  return <span className="mb-5 h-0.5 flex-1 rounded-full bg-[#0f172a]" />
}

/** Cảnh đường đêm vẽ bằng SVG; bật "nhiễu" thì phủ hạt nhiễu và khung bỏ sót màu đỏ. */
function RoadScene({ attacked }: { attacked: boolean }) {
  return (
    <svg viewBox="0 0 400 240" className="block w-full">
      <defs>
        <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#312e81" />
          <stop offset="1" stopColor="#7c3aed" />
        </linearGradient>
        <linearGradient id="road" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#334155" />
          <stop offset="1" stopColor="#0f172a" />
        </linearGradient>
        <filter id="noise">
          <feTurbulence type="fractalNoise" baseFrequency="1.4" numOctaves="2" seed="4" />
          <feColorMatrix values="0 0 0 0 1  0 0 0 0 0.3  0 0 0 0 0.8  0 0 0 0.9 0" />
        </filter>
      </defs>
      <rect width="400" height="240" fill="url(#sky)" />
      <circle cx="320" cy="48" r="16" fill="#fde68a" opacity="0.9" />
      <path
        d="M0 140 L70 96 L130 128 L210 82 L290 126 L340 104 L400 132 L400 150 L0 150Z"
        fill="#4c1d95"
      />
      <path d="M0 150 H400 V240 H0Z" fill="#1e1b4b" />
      <path d="M150 150 L250 150 L400 240 L0 240Z" fill="url(#road)" />
      <path d="M200 156 V170 M200 182 V200 M200 214 V240" stroke="#ec4899" strokeWidth="4" />
      {/* Ô tô */}
      <g transform="translate(226 160)">
        <rect x="0" y="16" width="96" height="30" rx="8" fill="#f1f5f9" />
        <path d="M14 18 L30 0 H70 L84 18Z" fill="#cbd5e1" />
        <rect x="34" y="4" width="16" height="12" rx="2" fill="#475569" />
        <rect x="54" y="4" width="16" height="12" rx="2" fill="#475569" />
        <circle cx="22" cy="46" r="9" fill="#0f172a" />
        <circle cx="74" cy="46" r="9" fill="#0f172a" />
        <rect x="88" y="24" width="8" height="6" rx="2" fill="#fde68a" />
      </g>
      {/* Biển báo */}
      <g transform="translate(70 120)">
        <rect x="8" y="22" width="4" height="50" fill="#94a3b8" />
        <path d="M10 0 L24 24 H-4Z" fill="#f59e0b" stroke="#0f172a" strokeWidth="2" />
      </g>

      <g style={{ transition: 'opacity .35s ease', opacity: attacked ? 1 : 0 }}>
        <rect width="400" height="240" filter="url(#noise)" opacity="0.38" />
        <rect
          x="220"
          y="154"
          width="108"
          height="62"
          fill="none"
          stroke="#f87171"
          strokeWidth="3"
          strokeDasharray="8 6"
          rx="3"
        />
        <rect x="220" y="132" width="98" height="20" rx="3" fill="#dc2626" />
        <text
          x="227"
          y="146"
          fontSize="12"
          fontWeight="700"
          fill="#fff"
          fontFamily="Inter Variable, sans-serif"
        >
          bỏ sót · 0.18
        </text>
      </g>
      <g style={{ transition: 'opacity .35s ease', opacity: attacked ? 0 : 1 }}>
        <rect
          x="220"
          y="154"
          width="108"
          height="62"
          fill="none"
          stroke="#38bdf8"
          strokeWidth="3"
          rx="3"
        />
        <rect x="220" y="132" width="86" height="20" rx="3" fill="#0284c7" />
        <text
          x="227"
          y="146"
          fontSize="12"
          fontWeight="700"
          fill="#fff"
          fontFamily="Inter Variable, sans-serif"
        >
          ô tô · 0.94
        </text>
        <rect
          x="58"
          y="116"
          width="44"
          height="80"
          fill="none"
          stroke="#38bdf8"
          strokeWidth="2.5"
          rx="3"
        />
      </g>
    </svg>
  )
}

function Starburst({ className }: { className?: string }) {
  const points = Array.from({ length: 24 }, (_, i) => {
    const r = i % 2 === 0 ? 48 : 34
    const a = (i / 24) * Math.PI * 2
    return `${(50 + Math.cos(a) * r).toFixed(1)},${(50 + Math.sin(a) * r).toFixed(1)}`
  }).join(' ')
  return (
    <svg viewBox="0 0 100 100" className={className}>
      <polygon
        points={points}
        fill="#fde68a"
        stroke="#0f172a"
        strokeWidth="3"
        strokeLinejoin="round"
      />
      <text
        x="50"
        y="57"
        textAnchor="middle"
        fontSize="20"
        fontWeight="900"
        fill="#0f172a"
        fontFamily="Inter Variable, sans-serif"
      >
        PGD
      </text>
    </svg>
  )
}

function Sparkle({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className}>
      <path
        d="M12 1 C13 8 16 11 23 12 C16 13 13 16 12 23 C11 16 8 13 1 12 C8 11 11 8 12 1Z"
        fill="#fff"
        stroke="#0f172a"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
    </svg>
  )
}
