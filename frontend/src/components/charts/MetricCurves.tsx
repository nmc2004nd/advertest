import { useState } from 'react'
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { StatusBadge } from '@/components/status/StatusBadge'
import { Button } from '@/components/ui/button'
import type { RunView } from '@/contracts/api'

import {
  type AttackCurve,
  axisValue,
  buildCurves,
  type CurvePoint,
  formatMetric,
  formatPercent,
  plotted,
} from './curves'

type Metric = 'map50' | 'asr'

const METRICS: Record<Metric, { title: string; format: (v: number | null) => string }> = {
  map50: { title: 'mAP@0.5 sau tấn công', format: formatMetric },
  asr: { title: 'Tỷ lệ tấn công thành công', format: formatPercent },
}

// Màu lấy từ biến theme (đổi theo chế độ sáng/tối).
const LINE = 'var(--foreground)'
const MUTED = 'var(--muted-foreground)'
const PARTIAL = 'var(--destructive)'

interface DotProps {
  cx?: number
  cy?: number
  payload?: CurvePoint
}

/** Điểm thường là chấm tròn đặc; run `partial` là hình thoi rỗng màu cảnh báo. */
function CurveDot({ cx, cy, payload }: DotProps) {
  if (cx === undefined || cy === undefined) return null
  if (payload?.partial) {
    return (
      <path
        d={`M${cx},${cy - 6} L${cx + 6},${cy} L${cx},${cy + 6} L${cx - 6},${cy} Z`}
        fill="var(--background)"
        stroke={PARTIAL}
        strokeWidth={2}
        data-partial="true"
      />
    )
  }
  return <circle cx={cx} cy={cy} r={4} fill={LINE} />
}

export const NORMALIZED_LABEL = 'Trục hoành chuẩn hóa (% dải cho phép)'

function CurveChart({
  curve,
  metric,
  cleanMap50,
  normalized,
}: {
  curve: AttackCurve
  metric: Metric
  cleanMap50: number | null
  normalized: boolean
}) {
  const { title, format } = METRICS[metric]
  const unit = curve.paramUnit ? ` (${curve.paramUnit})` : ''
  const axisLabel = normalized
    ? `% dải ${curve.paramName} (level / ${curve.paramMax})`
    : `${curve.paramName}${unit}`
  const data = plotted(curve, metric).map((p) => ({
    ...p,
    x: axisValue(curve, p.level, normalized),
  }))
  if (plotted(curve, metric).length === 0) {
    return (
      <figure className="min-w-0 space-y-2">
        <figcaption className="text-sm font-medium">{title}</figcaption>
        <p className="text-sm text-muted-foreground">Chưa có run nào có metric để vẽ.</p>
      </figure>
    )
  }
  return (
    <figure className="min-w-0 space-y-2">
      <figcaption className="text-sm font-medium">{title}</figcaption>
      <div className="h-56 w-full" aria-hidden="true">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 16, bottom: 20, left: 0 }}>
            <CartesianGrid stroke={MUTED} strokeOpacity={0.25} />
            <XAxis
              dataKey="x"
              type="number"
              domain={normalized ? [0, 100] : ['dataMin', 'dataMax']}
              unit={normalized ? '%' : undefined}
              stroke={MUTED}
              label={{ value: axisLabel, position: 'insideBottom', offset: -12 }}
            />
            <YAxis domain={[0, 1]} stroke={MUTED} width={40} />
            <Tooltip
              formatter={(value) => format(typeof value === 'number' ? value : null)}
              labelFormatter={(x) =>
                normalized
                  ? `${Number(x).toFixed(1)}% dải ${curve.paramName}`
                  : `${curve.paramName} = ${String(x)}`
              }
            />
            {metric === 'map50' && cleanMap50 !== null && (
              <ReferenceLine
                y={cleanMap50}
                stroke={MUTED}
                strokeDasharray="6 4"
                label={{
                  value: `mAP sạch ${formatMetric(cleanMap50)}`,
                  position: 'insideTopRight',
                }}
              />
            )}
            <Line
              dataKey={metric}
              stroke={LINE}
              strokeWidth={2}
              isAnimationActive={false}
              dot={<CurveDot />}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </figure>
  )
}

/** Bảng số liệu đi kèm biểu đồ (khả năng tiếp cận, đọc giá trị chính xác). */
export function CurveTable({
  curve,
  normalized = false,
}: {
  curve: AttackCurve
  normalized?: boolean
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[28rem] text-sm">
        <caption className="sr-only">Số liệu của {curve.name}</caption>
        <thead className="text-left text-muted-foreground">
          <tr>
            <th scope="col" className="py-1 pr-3 font-medium">
              {curve.paramName}
              {curve.paramUnit ? ` (${curve.paramUnit})` : ''}
            </th>
            {normalized && (
              <th scope="col" className="py-1 pr-3 font-medium">
                % dải
              </th>
            )}
            <th scope="col" className="py-1 pr-3 font-medium">
              mAP@0.5
            </th>
            <th scope="col" className="py-1 pr-3 font-medium">
              Mức sụt
            </th>
            <th scope="col" className="py-1 pr-3 font-medium">
              Tấn công thành công
            </th>
            <th scope="col" className="py-1 font-medium">
              Trạng thái
            </th>
          </tr>
        </thead>
        <tbody>
          {curve.points.map((point) => (
            <tr key={point.runId} className="border-t" data-partial={point.partial || undefined}>
              <td className="py-1 pr-3 tabular-nums">{point.level}</td>
              {normalized && (
                <td className="py-1 pr-3 tabular-nums">
                  {axisValue(curve, point.level, true).toFixed(1)}%
                </td>
              )}
              <td className="py-1 pr-3 tabular-nums">{formatMetric(point.map50)}</td>
              <td className="py-1 pr-3 tabular-nums">{formatPercent(point.relativeDrop)}</td>
              <td className="py-1 pr-3 tabular-nums">{formatPercent(point.asr)}</td>
              <td className="py-1">
                <span className="inline-flex flex-wrap items-center gap-1">
                  <StatusBadge kind="run" status={point.status} />
                  {point.partial && (
                    <span className="text-xs text-destructive">◇ một phần ảnh</span>
                  )}
                  {point.earlyStop && (
                    <span className="text-xs text-muted-foreground">
                      dừng sớm: đã sụp ở level thấp hơn
                    </span>
                  )}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function AttackBlock({
  curve,
  cleanMap50,
  normalized,
}: {
  curve: AttackCurve
  cleanMap50: number | null
  normalized: boolean
}) {
  // Điện thoại: một biểu đồ một lúc, chuyển bằng tab; từ md trở lên hiện cả hai.
  const [metric, setMetric] = useState<Metric>('map50')
  const hasPartial = curve.points.some((p) => p.partial)
  return (
    <section className="space-y-3 rounded-lg border p-3 md:p-4" aria-label={curve.name}>
      <h3 className="font-semibold">
        {curve.name}{' '}
        <span className="text-sm font-normal text-muted-foreground">v{curve.version}</span>
      </h3>
      <div role="tablist" aria-label={`Biểu đồ của ${curve.name}`} className="flex gap-2 md:hidden">
        {(Object.keys(METRICS) as Metric[]).map((key) => (
          <Button
            key={key}
            role="tab"
            aria-selected={metric === key}
            variant={metric === key ? 'default' : 'outline'}
            onClick={() => setMetric(key)}
          >
            {key === 'map50' ? 'mAP@0.5' : 'Tấn công thành công'}
          </Button>
        ))}
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        {(Object.keys(METRICS) as Metric[]).map((key) => (
          <div key={key} className={metric === key ? 'block' : 'hidden md:block'}>
            <CurveChart
              curve={curve}
              metric={key}
              cleanMap50={cleanMap50}
              normalized={normalized}
            />
          </div>
        ))}
      </div>
      {hasPartial && (
        <p className="text-xs text-muted-foreground">
          <span className="text-destructive">◇</span> Run dừng giữa chừng: metric chỉ tính trên phần
          ảnh đã xử lý.
        </p>
      )}
      <CurveTable curve={curve} normalized={normalized} />
    </section>
  )
}

/** Đường cong metric theo level, mỗi attack một khối (trục x theo đơn vị của attack). */
export function MetricCurves({
  runs,
  cleanMap50,
  initialNormalized = false,
}: {
  runs: RunView[]
  cleanMap50: number | null
  /** Trạng thái ban đầu của công tắc trục chuẩn hóa (test render tĩnh). */
  initialNormalized?: boolean
}) {
  // Phase 6 (người dùng chốt ở Group 6): một công tắc cho mọi biểu đồ; bật thì trục hoành là
  // level / max (%), miền cố định 0–100% để so các attack khác đơn vị cạnh nhau.
  const [normalized, setNormalized] = useState(initialNormalized)
  const curves = buildCurves(runs)
  if (curves.length === 0) {
    return <p className="text-muted-foreground">Chưa có run nào.</p>
  }
  return (
    <div className="space-y-4">
      <label className="flex min-h-11 cursor-pointer items-center gap-3">
        <input
          type="checkbox"
          role="switch"
          className="size-5"
          checked={normalized}
          onChange={(event) => setNormalized(event.target.checked)}
        />
        <span className="text-sm font-medium">{NORMALIZED_LABEL}</span>
      </label>
      {curves.map((curve) => (
        <AttackBlock
          key={curve.attackSpecId}
          curve={curve}
          cleanMap50={cleanMap50}
          normalized={normalized}
        />
      ))}
    </div>
  )
}
