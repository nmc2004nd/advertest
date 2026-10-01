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

function CurveChart({
  curve,
  metric,
  cleanMap50,
}: {
  curve: AttackCurve
  metric: Metric
  cleanMap50: number | null
}) {
  const { title, format } = METRICS[metric]
  const unit = curve.paramUnit ? ` (${curve.paramUnit})` : ''
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
          <LineChart
            data={plotted(curve, metric)}
            margin={{ top: 8, right: 16, bottom: 20, left: 0 }}
          >
            <CartesianGrid stroke={MUTED} strokeOpacity={0.25} />
            <XAxis
              dataKey="level"
              type="number"
              domain={['dataMin', 'dataMax']}
              stroke={MUTED}
              label={{ value: `${curve.paramName}${unit}`, position: 'insideBottom', offset: -12 }}
            />
            <YAxis domain={[0, 1]} stroke={MUTED} width={40} />
            <Tooltip
              formatter={(value) => format(typeof value === 'number' ? value : null)}
              labelFormatter={(level) => `${curve.paramName} = ${String(level)}`}
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
export function CurveTable({ curve }: { curve: AttackCurve }) {
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

function AttackBlock({ curve, cleanMap50 }: { curve: AttackCurve; cleanMap50: number | null }) {
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
            <CurveChart curve={curve} metric={key} cleanMap50={cleanMap50} />
          </div>
        ))}
      </div>
      {hasPartial && (
        <p className="text-xs text-muted-foreground">
          <span className="text-destructive">◇</span> Run dừng giữa chừng: metric chỉ tính trên phần
          ảnh đã xử lý.
        </p>
      )}
      <CurveTable curve={curve} />
    </section>
  )
}

/** Đường cong metric theo level, mỗi attack một khối (trục x theo đơn vị của attack). */
export function MetricCurves({ runs, cleanMap50 }: { runs: RunView[]; cleanMap50: number | null }) {
  const curves = buildCurves(runs)
  if (curves.length === 0) {
    return <p className="text-muted-foreground">Chưa có run nào.</p>
  }
  return (
    <div className="space-y-4">
      {curves.map((curve) => (
        <AttackBlock key={curve.attackSpecId} curve={curve} cleanMap50={cleanMap50} />
      ))}
    </div>
  )
}
