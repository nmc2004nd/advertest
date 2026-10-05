/**
 * Minh họa viền mực cho phần đầu các trang (tham khảo beehiiv): mỗi trang một hình kể đúng việc
 * của trang đó. Thuần trang trí: chỗ dùng đặt `aria-hidden`.
 */
import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

const INK = '#0f172a'

function Card({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <div className={cn('ink-card relative bg-white p-4 text-[#0f172a]', className)}>{children}</div>
  )
}

function Lines({ widths }: { widths: string[] }) {
  return (
    <div className="flex flex-col gap-1.5">
      {widths.map((w, i) => (
        <span
          key={i}
          className={cn('h-2 rounded-full', i === 0 ? 'bg-[#0f172a]' : 'bg-[#cbd5e1]')}
          style={{ width: w }}
        />
      ))}
    </div>
  )
}

export function Squiggle({ className, color = '#7c3aed' }: { className?: string; color?: string }) {
  return (
    <svg viewBox="0 0 80 60" className={className} fill="none">
      <path
        d="M6 40c10-22 34-32 44-18 8 11-6 26-16 18-9-7 4-24 22-24 9 0 16 5 18 12"
        stroke={color}
        strokeWidth="3"
        strokeLinecap="round"
      />
    </svg>
  )
}

export function Sparkle({ className, fill = '#fff' }: { className?: string; fill?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className}>
      <path
        d="M12 1C13 8 16 11 23 12 16 13 13 16 12 23 11 16 8 13 1 12 8 11 11 8 12 1Z"
        fill={fill}
        stroke={INK}
        strokeWidth="1.4"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function Check({ last = false }: { last?: boolean }) {
  return (
    <span
      className={cn(
        'flex size-7 shrink-0 items-center justify-center rounded-full border-2 border-[#0f172a] bg-white',
        last && 'bg-[#fbcfe8]',
      )}
    >
      {last ? (
        <svg viewBox="0 0 24 24" className="size-4" fill="none" stroke={INK} strokeWidth="2.2">
          <path d="M4 20l5-14 9 9z" strokeLinejoin="round" />
          <path d="M14 4l1 2M19 6l-2 1M18 10h2" strokeLinecap="round" />
        </svg>
      ) : (
        <svg viewBox="0 0 24 24" className="size-3.5" fill="none" stroke="#db2777" strokeWidth="3">
          <path d="M5 12l5 5 9-10" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      )}
    </span>
  )
}

/** Experiment: biểu đồ mAP tụt dần theo mức nhiễu, chuỗi bước ✓ tới pháo giấy. */
export function ExperimentArt() {
  const bars = [92, 74, 51, 30]
  return (
    <div className="relative w-[300px]">
      <Card className="rotate-[-2deg]">
        <div className="flex items-start justify-between gap-3">
          <Lines widths={['110px', '76px']} />
          <Squiggle className="-mt-2 h-10 w-14" color="#2563eb" />
        </div>
        <div className="mt-3 flex h-[72px] items-end gap-3 border-b-2 border-[#0f172a] px-1">
          {bars.map((h, i) => (
            <span
              key={i}
              className="flex-1 rounded-t-md border-2 border-b-0 border-[#0f172a]"
              style={{
                height: `${h}%`,
                background: ['#93c5fd', '#a5b4fc', '#c4b5fd', '#f9a8d4'][i],
              }}
            />
          ))}
        </div>
        <div className="mt-1 flex justify-between px-1 text-[10px] font-semibold text-[#475569]">
          <span>gốc</span>
          <span>eps 2</span>
          <span>eps 4</span>
          <span>eps 8</span>
        </div>
      </Card>
      <div className="absolute -bottom-5 left-2 right-2 flex items-center">
        {[0, 1, 2].map((i) => (
          <span key={i} className="flex flex-1 items-center">
            <Check />
            <span className="h-0.5 flex-1 bg-[#db2777]" />
          </span>
        ))}
        <Check last />
      </div>
    </div>
  )
}

/** Protocol: tờ luật có khóa, ba ô quy tắc, chip mức nhiễu (tham khảo thẻ biểu mẫu beehiiv). */
export function ProtocolArt() {
  return (
    <div className="relative w-[290px]">
      <Card className="rotate-[1.5deg]">
        <div className="flex items-center gap-3">
          <span className="flex size-8 items-center justify-center rounded-lg bg-[#ec4899] text-white">
            <svg
              viewBox="0 0 24 24"
              className="size-4"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.4"
            >
              <rect x="5" y="11" width="14" height="10" rx="2" />
              <path d="M8 11V8a4 4 0 0 1 8 0v3" />
            </svg>
          </span>
          <Lines widths={['120px', '80px']} />
        </div>
        <div className="mt-3 flex items-center gap-2 rounded-full bg-[#f1f5f9] p-1">
          <span className="h-4 flex-1" />
          <span className="h-4 w-20 rounded-full bg-[#f472b6]" />
        </div>
        <span className="mx-auto mt-3 block h-px bg-[#cbd5e1]" />
        <div className="mt-3 grid grid-cols-3 gap-2">
          {['FGSM', '≤ 60%', '5 ảnh'].map((t) => (
            <span
              key={t}
              className="flex h-12 flex-col justify-between rounded-lg bg-[#f5f3ff] p-1.5 text-[11px] font-bold"
            >
              <span className="text-[#7c3aed]">“</span>
              {t}
            </span>
          ))}
        </div>
      </Card>
      <span className="ink-chip float absolute -right-6 top-14 flex items-center gap-1.5 px-2.5 py-1 text-[11.5px] font-bold">
        <span className="size-3 rounded-sm bg-[#2563eb]" />
        eps 2, 4
      </span>
      <Sparkle className="absolute -left-6 -top-5 size-8" />
    </div>
  )
}

/** Report: bản chính thức có con dấu, mã hash, chip xác minh. */
export function ReportArt() {
  return (
    <div className="relative w-[280px]">
      <Card className="rotate-[-1.5deg]">
        <Lines widths={['130px', '170px', '150px']} />
        <div className="mt-3 flex gap-3">
          <span className="flex h-16 flex-1 items-center justify-center rounded-lg bg-[#eef2ff]">
            <svg
              viewBox="0 0 24 24"
              className="size-6"
              fill="none"
              stroke="#6366f1"
              strokeWidth="2"
            >
              <rect x="3" y="5" width="18" height="14" rx="2" />
              <path d="M3 16l5-5 4 4 3-3 6 6" />
            </svg>
          </span>
          <span className="flex flex-1 flex-col justify-center gap-1.5">
            <span className="h-1.5 w-full rounded-full bg-[#0f172a]" />
            <span className="h-1.5 w-3/4 rounded-full bg-[#cbd5e1]" />
            <span className="h-1.5 w-5/6 rounded-full bg-[#cbd5e1]" />
          </span>
        </div>
      </Card>
      <span className="absolute -right-5 -top-6 flex size-20 rotate-12 items-center justify-center rounded-full border-2 border-dashed border-[#db2777] bg-[#fdf2f8] text-center text-[10px] leading-tight font-black text-[#be185d]">
        BẢN
        <br />
        CHÍNH
        <br />
        THỨC
      </span>
      <span className="ink-chip float-slow absolute -bottom-5 -left-6 flex items-center gap-1.5 px-2.5 py-1 font-mono text-[11px] font-bold">
        <svg viewBox="0 0 24 24" className="size-3.5" fill="none" stroke="#16a34a" strokeWidth="3">
          <path d="M5 12l5 5 9-10" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        sha256 9f3a…c1
      </span>
    </div>
  )
}

/** Duyệt: hai ảnh trước/sau tấn công với khung nhận diện, chip "đang xem". */
export function ReviewArt() {
  return (
    <div className="relative w-[290px]">
      <Card className="rotate-[1deg]">
        <div className="grid grid-cols-2 gap-2.5">
          {[
            { label: 'ô tô 0.94', color: '#0284c7', dashed: false },
            { label: 'bỏ sót', color: '#dc2626', dashed: true },
          ].map((b) => (
            <span
              key={b.label}
              className="relative h-20 overflow-hidden rounded-lg bg-gradient-to-b from-[#c7d2fe] to-[#64748b]"
            >
              <span
                className="absolute bottom-3 left-1/2 h-7 w-12 -translate-x-1/2 rounded border-2"
                style={{ borderColor: b.color, borderStyle: b.dashed ? 'dashed' : 'solid' }}
              />
              <span
                className="absolute bottom-10 left-1/2 -translate-x-1/2 rounded px-1 text-[9px] font-bold whitespace-nowrap text-white"
                style={{ background: b.color }}
              >
                {b.label}
              </span>
            </span>
          ))}
        </div>
        <div className="mt-3 flex items-center gap-2">
          {['Nhỏ', 'Chấp nhận được'].map((t, i) => (
            <span
              key={t}
              className={cn(
                'rounded-full border-2 border-[#0f172a] px-2 py-0.5 text-[10.5px] font-bold',
                i === 1 ? 'bg-[#bbf7d0]' : 'bg-white',
              )}
            >
              {t}
            </span>
          ))}
          <span className="ml-auto rounded-md bg-[#f1f5f9] px-1.5 text-[10px] font-bold text-[#475569]">
            Ctrl ↵
          </span>
        </div>
      </Card>
      <Sparkle className="absolute -right-4 -top-4 size-7" fill="#fde68a" />
    </div>
  )
}

/** Người dùng: ba người chờ duyệt, người đầu đã được gán vai trò. */
export function UsersArt() {
  const people = [
    { c: '#2563eb', w: '92px', ok: true },
    { c: '#db2777', w: '70px', ok: false },
    { c: '#7c3aed', w: '84px', ok: false },
  ]
  return (
    <div className="relative w-[270px]">
      <Card className="flex flex-col gap-2.5 rotate-[-1deg]">
        {people.map((p, i) => (
          <span key={i} className="flex items-center gap-3">
            <span
              className="size-8 rounded-full border-2 border-[#0f172a]"
              style={{ background: p.c }}
            />
            <span className="h-2 rounded-full bg-[#cbd5e1]" style={{ width: p.w }} />
            <span
              className={cn(
                'ml-auto rounded-full border-2 border-[#0f172a] px-2 text-[10.5px] font-bold',
                p.ok ? 'bg-[#bbf7d0]' : 'bg-white',
              )}
            >
              {p.ok ? 'Đã duyệt' : 'Chờ'}
            </span>
          </span>
        ))}
      </Card>
      <Sparkle className="absolute -left-5 -bottom-4 size-7" fill="#fbcfe8" />
    </div>
  )
}

/** Máy bay giấy với đường bay nét đứt (tham khảo beehiiv), dùng trên nền tối. */
export function PlaneArt({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 260 170" className={className} fill="none">
      <path
        d="M10 150c40-6 70-30 58-58-10-24-48-12-36 14 14 30 70 18 104-22"
        stroke="#fff"
        strokeOpacity=".7"
        strokeWidth="2.5"
        strokeDasharray="7 7"
        strokeLinecap="round"
      />
      <path
        d="M150 70l90-50-28 104-30-30-32-24z M182 94l-6 34 18-22"
        stroke="#fff"
        strokeWidth="5"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  )
}
