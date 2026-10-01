import {
  CartesianGrid,
  ComposedChart,
  LabelList,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import type { TrajectoryPoint } from '@/contracts/api'

import {
  attackName,
  displayUnit,
  dropLabel,
  formatLevel,
  formatNumber,
  type SearchAttack,
  trajectoryRows,
} from './breakpoints'
import { formatPercent } from './curves'

// Màu lấy từ biến theme (đổi theo chế độ sáng/tối).
const LINE = 'var(--foreground)'
const MUTED = 'var(--muted-foreground)'
const CI = 'var(--destructive)'

interface DotProps {
  cx?: number
  cy?: number
  payload?: TrajectoryPoint
}

/** Điểm trên tập con rỗng ruột, trên toàn slice đặc. */
function TrajectoryDot({ cx, cy, payload }: DotProps) {
  if (cx === undefined || cy === undefined) return null
  const full = payload?.scope === 'full'
  return (
    <circle
      cx={cx}
      cy={cy}
      r={5}
      fill={full ? LINE : 'var(--background)'}
      stroke={LINE}
      strokeWidth={2}
      data-scope={payload?.scope}
    />
  )
}

export const TRAJECTORY_LEGEND =
  '○ tập con · ● toàn slice · số: thứ tự đánh giá · nét đứt: ngưỡng · vùng xám: khoảng hiện tại · vùng đỏ: khoảng tin cậy 95% của điểm gãy'

/** Biểu đồ quỹ đạo tìm ngưỡng (Recharts; ẩn với trình đọc màn hình, bảng số liệu đi kèm). */
function TrajectoryChart({ attack }: { attack: SearchAttack }) {
  const result = attack.result
  if (!result) return null
  const points = trajectoryRows(result).filter((p) => p.drop !== null)
  const [a, b] = result.bracket
  const ci = result.confidence_interval
  const unit = displayUnit(attack.spec)
  const param = attack.spec?.paramName ?? 'level'
  if (points.length === 0) {
    return <p className="text-sm text-muted-foreground">Chưa có điểm nào có metric để vẽ.</p>
  }
  return (
    <div className="h-64 w-full" aria-hidden="true">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart margin={{ top: 16, right: 16, bottom: 20, left: 0 }}>
          <CartesianGrid stroke={MUTED} strokeOpacity={0.25} />
          <XAxis
            dataKey="level"
            type="number"
            domain={[attack.config.lo, attack.config.hi]}
            stroke={MUTED}
            label={{
              value: `${param}${unit ? ` (${unit})` : ''}`,
              position: 'insideBottom',
              offset: -12,
            }}
          />
          <YAxis
            dataKey="drop"
            type="number"
            domain={[(min: number) => Math.min(0, min), (max: number) => Math.max(1, max)]}
            stroke={MUTED}
            width={40}
          />
          <Tooltip
            formatter={(value, name) =>
              name === 'drop'
                ? [formatPercent(typeof value === 'number' ? value : null), dropLabel(result)]
                : [formatLevel(Number(value), unit), param]
            }
            labelFormatter={() => ''}
          />
          <ReferenceArea x1={a} x2={b} fill={MUTED} fillOpacity={0.15} />
          {ci && (
            <ReferenceArea
              x1={ci[0]}
              x2={ci[1]}
              fill={CI}
              fillOpacity={0.12}
              stroke={CI}
              strokeDasharray="4 3"
            />
          )}
          <ReferenceLine
            y={result.threshold}
            stroke={LINE}
            strokeDasharray="6 4"
            label={{
              value: `Ngưỡng ${formatPercent(result.threshold)}`,
              position: 'insideTopRight',
            }}
          />
          <Scatter data={points} dataKey="drop" shape={<TrajectoryDot />} isAnimationActive={false}>
            <LabelList dataKey="order" position="top" />
          </Scatter>
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}

/** Bảng số liệu của quỹ đạo (đọc giá trị chính xác, khả năng tiếp cận). */
export function TrajectoryTable({ attack }: { attack: SearchAttack }) {
  const result = attack.result
  if (!result) return null
  const unit = displayUnit(attack.spec)
  const param = attack.spec?.paramName ?? 'level'
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[30rem] text-sm">
        <caption className="sr-only">Quỹ đạo tìm ngưỡng của {attackName(attack)}</caption>
        <thead className="text-left text-muted-foreground">
          <tr>
            <th scope="col" className="py-1 pr-3 font-medium">
              Thứ tự
            </th>
            <th scope="col" className="py-1 pr-3 font-medium">
              {param}
              {unit ? ` (${unit})` : ''}
            </th>
            <th scope="col" className="py-1 pr-3 font-medium">
              Phạm vi
            </th>
            <th scope="col" className="py-1 pr-3 font-medium">
              {dropLabel(result)}
            </th>
            <th scope="col" className="py-1 pr-3 font-medium">
              KTC 95%
            </th>
            <th scope="col" className="py-1 font-medium">
              Ghi chú
            </th>
          </tr>
        </thead>
        <tbody>
          {trajectoryRows(result).map((point) => (
            <tr key={point.order} className="border-t" data-scope={point.scope}>
              <td className="py-1 pr-3 tabular-nums">{point.order}</td>
              <td className="py-1 pr-3 tabular-nums">{formatNumber(point.level)}</td>
              <td className="py-1 pr-3">{point.scope === 'full' ? 'Toàn slice' : 'Tập con'}</td>
              <td className="py-1 pr-3 tabular-nums">{formatPercent(point.drop)}</td>
              <td className="py-1 pr-3 tabular-nums">
                {point.drop_ci
                  ? `${formatPercent(point.drop_ci[0])}–${formatPercent(point.drop_ci[1])}`
                  : '—'}
              </td>
              <td className="py-1 text-muted-foreground">
                {point.synthetic ? 'Tổng hợp (không chạy): mức sụt 0 theo định nghĩa' : ''}
                {!point.synthetic && point.drop === null ? 'Run không có metric' : ''}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** Quỹ đạo của một attack: biểu đồ, chú giải, bảng số liệu. */
export function SearchTrajectory({ attack }: { attack: SearchAttack }) {
  if (!attack.result) return null
  return (
    <figure className="min-w-0 space-y-2" aria-label={`Quỹ đạo của ${attackName(attack)}`}>
      <figcaption className="text-sm font-medium">
        Quỹ đạo: {dropLabel(attack.result).toLowerCase()} theo level
      </figcaption>
      <TrajectoryChart attack={attack} />
      <p className="text-xs text-muted-foreground">{TRAJECTORY_LEGEND}</p>
      <TrajectoryTable attack={attack} />
    </figure>
  )
}
