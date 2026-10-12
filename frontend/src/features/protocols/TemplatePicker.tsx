import { Camera, CloudFog, LayoutTemplate, type LucideIcon, ShieldCheck, Zap } from 'lucide-react'

import type { ProtocolTemplate } from '@/contracts/api'
import { cn } from '@/lib/utils'

type Key = ProtocolTemplate['key']

const TEMPLATE_LOOK: Record<Key, { icon: LucideIcon; tile: string }> = {
  quick: { icon: Zap, tile: '[--tile-bg:#fce7f3] [--tile-fg:#be185d]' },
  front_camera: { icon: Camera, tile: '[--tile-bg:#f5f3ff] [--tile-fg:#6d28d9]' },
  weather: { icon: CloudFog, tile: '[--tile-bg:#e0f2fe] [--tile-fg:#0369a1]' },
  full: { icon: ShieldCheck, tile: '[--tile-bg:#dcfce7] [--tile-fg:#15803d]' },
}

/** Ngưỡng mức sụt gợi ý theo độ chặt (requirements.md Phase R2, Gợi ý tiêu chí). */
const STRICTNESS: Record<ProtocolTemplate['strictness'], string> = {
  lenient: 'Sụt tối đa 50% ở level giữa',
  standard: 'Sụt tối đa 30% ở level giữa',
  strict: 'Sụt tối đa 15% ở level giữa',
}

function attackSummary(template: ProtocolTemplate): string {
  const names = template.attacks.map((a) => a.attack_spec_name)
  const shown = names.slice(0, 3).join(', ')
  return names.length > 3 ? `${shown} và ${names.length - 3} attack khác` : shown
}

/** Thẻ mẫu protocol (Phase R2: mẫu chỉ điền sẵn form, người dùng vẫn sửa trước khi tạo). */
export function TemplatePicker({
  templates,
  selected,
  loading,
  error,
  onPick,
}: {
  templates: ProtocolTemplate[]
  selected: Key | null
  loading: Key | null
  error: string | null
  onPick: (key: Key) => void
}) {
  if (templates.length === 0) return null
  return (
    <section className="space-y-2" aria-labelledby="mau-protocol">
      <div className="flex items-center gap-2">
        <LayoutTemplate aria-hidden="true" className="size-4 text-muted-foreground" />
        <h3 id="mau-protocol" className="font-semibold">
          Bắt đầu từ mẫu
        </h3>
      </div>
      <p className="text-sm text-muted-foreground">
        Chọn một mẫu để điền sẵn cả form. Bạn vẫn sửa được mọi ô bên dưới.
      </p>
      <div
        role="radiogroup"
        aria-label="Mẫu protocol"
        className="grid gap-2 md:grid-cols-2 xl:grid-cols-4"
      >
        {templates.map((t) => {
          const { icon: Icon, tile } = TEMPLATE_LOOK[t.key]
          const on = selected === t.key
          return (
            <button
              key={t.key}
              type="button"
              role="radio"
              aria-checked={on}
              aria-busy={loading === t.key ? true : undefined}
              disabled={loading !== null}
              onClick={() => onPick(t.key)}
              className={cn(
                'flex flex-col gap-1.5 rounded-xl border bg-surface-solid p-3.5 text-left transition-[border-color,box-shadow] duration-150 focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none disabled:cursor-wait',
                on ? 'border-navy ring-1 ring-navy' : 'border-line hover:border-input',
              )}
            >
              <span className="flex items-center gap-2.5">
                <span className={cn('tile size-8', tile)} aria-hidden="true">
                  <Icon className="size-4" />
                </span>
                <span className="flex-1 font-semibold">{t.title}</span>
                <span
                  aria-hidden="true"
                  className={cn(
                    'size-4 shrink-0 rounded-full border-2',
                    on ? 'border-navy bg-navy' : 'border-input',
                  )}
                />
              </span>
              <span className="text-sm leading-5 text-muted-foreground">
                {loading === t.key ? 'Đang điền form…' : t.description}
              </span>
              <ul className="mt-1 space-y-0.5 text-[13px] leading-5">
                {[
                  attackSummary(t),
                  STRICTNESS[t.strictness],
                  `Slice tối thiểu ${t.min_slice_size} ảnh`,
                ].map((line) => (
                  <li key={line} className="flex gap-1.5">
                    <span
                      aria-hidden="true"
                      className="mt-2 size-1 shrink-0 rounded-full bg-current"
                    />
                    {line}
                  </li>
                ))}
              </ul>
            </button>
          )
        })}
      </div>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
    </section>
  )
}
