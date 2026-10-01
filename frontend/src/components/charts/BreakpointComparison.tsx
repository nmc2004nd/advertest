import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  ResponsiveContainer,
  XAxis,
  YAxis,
} from 'recharts'

import { StatusBadge } from '@/components/status/StatusBadge'

import { comparisonRows, type SearchAttack } from './breakpoints'

const BAR = 'var(--foreground)'
const MUTED = 'var(--muted-foreground)'

/**
 * So sánh điểm gãy giữa các attack, chuẩn hóa về % dải của spec (level / max): càng nhỏ càng dễ
 * gãy. Attack không có điểm gãy không có cột, vẫn có trong bảng.
 */
export function BreakpointComparison({ attacks }: { attacks: SearchAttack[] }) {
  const rows = comparisonRows(attacks)
  const bars = rows.filter((row) => row.value !== null)
  return (
    <section className="space-y-2" aria-labelledby="so-sanh-diem-gay">
      <h4 id="so-sanh-diem-gay" className="text-sm font-medium">
        So sánh điểm gãy (% dải của spec, càng nhỏ càng dễ gãy)
      </h4>
      {bars.length > 0 && (
        <div style={{ height: 40 + bars.length * 32 }} className="w-full" aria-hidden="true">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={bars}
              layout="vertical"
              margin={{ top: 4, right: 88, bottom: 4, left: 0 }}
            >
              <CartesianGrid stroke={MUTED} strokeOpacity={0.25} horizontal={false} />
              <XAxis type="number" domain={[0, 100]} unit="%" stroke={MUTED} />
              <YAxis type="category" dataKey="name" width={96} stroke={MUTED} />
              <Bar dataKey="value" fill={BAR} isAnimationActive={false}>
                <LabelList dataKey="label" position="right" />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="w-full min-w-[22rem] text-left text-sm">
          <caption className="sr-only">Điểm gãy chuẩn hóa theo attack</caption>
          <thead className="text-muted-foreground">
            <tr>
              <th scope="col" className="py-1 pr-3 font-medium">
                Attack
              </th>
              <th scope="col" className="py-1 pr-3 font-medium">
                Trạng thái
              </th>
              <th scope="col" className="py-1 font-medium">
                Điểm gãy (% dải)
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.attackSpecId} className="border-t" data-status={row.status ?? undefined}>
                <td className="py-1 pr-3 font-medium">{row.name}</td>
                <td className="py-1 pr-3">
                  {row.status ? <StatusBadge kind="search" status={row.status} /> : '—'}
                </td>
                <td className="py-1 tabular-nums">{row.label}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
