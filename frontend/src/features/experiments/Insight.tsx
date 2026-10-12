import { ChevronRight } from 'lucide-react'
import { type ReactNode, useId } from 'react'
import { useSearchParams } from 'react-router'

import { AttackTile } from '@/components/AttackTile'
import { RobustnessMatrix } from '@/components/charts/RobustnessMatrix'
import { percent } from '@/components/charts/sentences'
import { formatNumber } from '@/components/charts/breakpoints'
import { Term } from '@/components/Term'
import type { AttackSpec, ExperimentInsight, Weakness } from '@/contracts/api'
import { PARTIAL_LABEL, WEAKNESS_NOTE } from '@/copy/charts'

import { displayNames } from './results'

/** Level kèm nhãn của metadata, ví dụ "eps 4" hoặc "vừa (3)". */
function levelText(weakness: Weakness, param: string | undefined): string {
  const value = formatNumber(weakness.level)
  if (weakness.level_label) return `${weakness.level_label} (${value})`
  return param ? `${param} ${value}` : `level ${value}`
}

function WeaknessRow({
  weakness,
  title,
  param,
  onOpen,
}: {
  weakness: Weakness
  title: string
  param: string | undefined
  onOpen: () => void
}) {
  const impact =
    weakness.kind === 'grid'
      ? `mAP@0.5 giảm ${percent(weakness.relative_drop ?? 0)}`
      : `điểm gãy ở ${formatNumber(weakness.breaking_point ?? weakness.level)}`
  return (
    <li>
      <button
        type="button"
        data-testid="weakness"
        data-attack={weakness.attack_name}
        data-level={weakness.level}
        onClick={onOpen}
        className="group flex min-h-11 w-full items-center gap-3 rounded-xl border border-line bg-surface-solid px-4 py-3 text-left transition-colors duration-150 hover:border-input hover:bg-surface-raised focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
      >
        <AttackTile spec={{ name: weakness.attack_name }} />
        <span className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="font-medium">
            {title} · {levelText(weakness, param)}
          </span>
          <span className="text-sm text-muted-foreground">
            <span className="font-semibold text-fail">{impact}</span>
            {weakness.class_name && weakness.class_relative_drop !== null && (
              <>
                {' '}
                · class {weakness.class_name} giảm {percent(weakness.class_relative_drop)}
              </>
            )}
          </span>
        </span>
        <span className="hidden text-sm text-cta sm:inline">Xem failure case</span>
        <ChevronRight aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
      </button>
    </li>
  )
}

/**
 * Đầu tab Kết quả (requirements.md Phase R3, Kết quả và insight): câu kết luận của backend, điểm
 * yếu chính (bấm để mở Failure case đã lọc), ma trận độ bền; `action` (nâng lên chính thức) ngay
 * dưới. Trạng thái `no_data` do `ResultsTab` xử lý.
 */
export function InsightSection({
  insight,
  catalog,
  action,
}: {
  insight: ExperimentInsight
  catalog: AttackSpec[]
  action?: ReactNode
}) {
  const [, setParams] = useSearchParams()
  const nameOf = displayNames(catalog)
  const paramOf = new Map(catalog.map((spec) => [spec.id, spec.primary_param.name]))
  // id sinh theo instance: trang review dựng tab Kết quả cạnh form có ô "Kết luận" (`#ket-luan`).
  const id = useId()
  return (
    <div className="space-y-6">
      <section className="panel space-y-2 p-5" aria-labelledby={`${id}-ket-luan`}>
        <div className="flex flex-wrap items-center gap-2">
          <h3 id={`${id}-ket-luan`} className="font-semibold">
            Kết luận
          </h3>
          {insight.partial && (
            <span className="rounded-full bg-threshold/12 px-2 py-0.5 text-xs font-semibold text-threshold">
              {PARTIAL_LABEL}
            </span>
          )}
        </div>
        <p data-testid="insight-conclusion" className="max-w-[72ch] text-[15px] leading-6">
          {insight.conclusion.text}
        </p>
        <p className="text-sm text-muted-foreground">
          Số liệu là <Term term="map" /> trên ảnh bị biến đổi so với ảnh sạch;{' '}
          <Term term="relative_drop" /> càng lớn thì model càng yếu ở attack đó.
        </p>
      </section>
      {insight.weaknesses.length > 0 && (
        <section className="space-y-3" aria-labelledby={`${id}-diem-yeu`}>
          <h3 id={`${id}-diem-yeu`} className="font-semibold">
            Điểm yếu chính
          </h3>
          <p className="text-sm text-muted-foreground">
            Mỗi dòng là một attack và <Term term="level" /> làm model sụt nhiều (với tìm ngưỡng là{' '}
            <Term term="breaking_point" />
            ). {WEAKNESS_NOTE}
          </p>
          <ul className="space-y-2">
            {insight.weaknesses.map((weakness) => (
              <WeaknessRow
                key={`${weakness.attack_spec_id}-${weakness.level}`}
                weakness={weakness}
                title={nameOf(weakness.attack_spec_id, weakness.attack_name)}
                param={paramOf.get(weakness.attack_spec_id)}
                onOpen={() =>
                  setParams(
                    {
                      tab: 'cases',
                      attack: weakness.attack_name,
                      level: String(weakness.level),
                    },
                    { replace: true },
                  )
                }
              />
            ))}
          </ul>
        </section>
      )}
      {insight.matrix.length > 0 && (
        <RobustnessMatrix
          rows={insight.matrix}
          bands={insight.bands}
          name={(row) => nameOf(row.attack_spec_id, row.attack_name)}
        />
      )}
      {action}
    </div>
  )
}
