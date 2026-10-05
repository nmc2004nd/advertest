import { cn } from '@/lib/utils'

/**
 * Logo: dấu tròn bốn ô của xe thử va chạm (crash test) đặt trong bốn góc khung nhận diện; một ô
 * vỡ thành điểm ảnh và làm đứt viền tròn, như lúc một attack khiến model nhìn sai.
 */
export function BrandMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 64 64" aria-hidden className={cn('shrink-0', className)}>
      <defs>
        <linearGradient id="brand-g" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#2563eb" />
          <stop offset="0.55" stopColor="#7c3aed" />
          <stop offset="1" stopColor="#ec4899" />
        </linearGradient>
        <clipPath id="brand-c">
          <circle cx="32" cy="32" r="17.5" />
        </clipPath>
      </defs>
      <rect width="64" height="64" rx="16" fill="url(#brand-g)" />
      <path
        d="M10 20v-10h10M44 10h10v10M54 44v10h-10M20 54h-10v-10"
        fill="none"
        stroke="#fff"
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M32 49.5A17.5 17.5 0 1 1 49.5 32"
        fill="none"
        stroke="#fff"
        strokeWidth="3"
        strokeLinecap="round"
      />
      <path
        d="M49.5 32A17.5 17.5 0 0 1 32 49.5"
        fill="none"
        stroke="#fff"
        strokeOpacity=".55"
        strokeWidth="3"
        strokeDasharray="2.6 3.4"
      />
      <rect x="14.5" y="14.5" width="17.5" height="17.5" fill="#fff" clipPath="url(#brand-c)" />
      <g fill="#fff">
        <rect x="33.2" y="33.2" width="4.6" height="4.6" rx=".8" />
        <rect x="38.6" y="33.2" width="4.6" height="4.6" rx=".8" />
        <rect x="33.2" y="38.6" width="4.6" height="4.6" rx=".8" />
        <rect x="44" y="34.4" width="4.6" height="4.6" rx=".8" fillOpacity=".8" />
        <rect x="39.8" y="40" width="4.6" height="4.6" rx=".8" fillOpacity=".8" />
        <rect x="34.4" y="44" width="4.6" height="4.6" rx=".8" fillOpacity=".8" />
        <rect x="47.2" y="42.6" width="3.8" height="3.8" rx=".7" fillOpacity=".55" />
        <rect x="42.6" y="47.2" width="3.8" height="3.8" rx=".7" fillOpacity=".55" />
        <rect x="50.6" y="49" width="3" height="3" rx=".6" fillOpacity=".35" />
      </g>
    </svg>
  )
}
