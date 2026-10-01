import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import type { AttackRankingEntry } from '@/contracts/api'
import { ATTACK_KIND_LABEL } from '@/lib/attack-kinds'

import { formatPercent } from './curves'
import { formatAuc, levelsText } from './ranking'

const BAR = 'var(--foreground)'
const MUTED = 'var(--muted-foreground)'

/** Biểu đồ cột `auc_drop` theo attack; attack không đủ dữ liệu không có cột (vẫn có trong bảng). */
function AucChart({ ranking }: { ranking: AttackRankingEntry[] }) {
  const data = ranking.filter((entry) => entry.auc_drop !== null)
  if (data.length === 0) return null
  return (
    <figure className="min-w-0 space-y-2">
      <figcaption className="text-sm font-medium">
        Diện tích mức sụt (auc_drop) theo attack
      </figcaption>
      <div style={{ height: 40 + data.length * 32 }} className="w-full" aria-hidden="true">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={data}
            layout="vertical"
            margin={{ top: 4, right: 16, bottom: 4, left: 0 }}
          >
            <CartesianGrid stroke={MUTED} strokeOpacity={0.25} horizontal={false} />
            <XAxis type="number" domain={[0, 1]} stroke={MUTED} />
            <YAxis type="category" dataKey="name" width={96} stroke={MUTED} />
            <Tooltip formatter={(value) => (typeof value === 'number' ? value.toFixed(3) : '')} />
            <Bar dataKey="auc_drop" fill={BAR} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </figure>
  )
}

const HEADERS = [
  'Hạng',
  'Attack',
  'Loại',
  'auc_drop',
  'Mức sụt lớn nhất',
  'Số level',
  'Độ phủ',
  'Ghi chú',
]

function Notes({ entry }: { entry: AttackRankingEntry }) {
  if (!entry.partial) return <span className="text-muted-foreground">—</span>
  return <span className="text-destructive">Có run dừng giữa chừng (metric một phần)</span>
}

/** Bảng: từ md trở lên. */
function RankingTable({ ranking }: { ranking: AttackRankingEntry[] }) {
  return (
    <div className="hidden overflow-x-auto rounded-xl border border-border md:block">
      <table className="w-full text-left text-sm">
        <caption className="sr-only">Bảng xếp hạng attack</caption>
        <thead className="bg-muted/50">
          <tr>
            {HEADERS.map((h) => (
              <th key={h} scope="col" className="px-3 py-2 font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {ranking.map((entry, i) => (
            <tr
              key={entry.attack_spec_id}
              className="border-t border-border align-top"
              data-partial={entry.partial || undefined}
            >
              <td className="px-3 py-2 tabular-nums">{i + 1}</td>
              <td className="px-3 py-2 font-medium">{entry.name}</td>
              <td className="px-3 py-2">{ATTACK_KIND_LABEL[entry.kind]}</td>
              <td className="px-3 py-2 tabular-nums">{formatAuc(entry.auc_drop)}</td>
              <td className="px-3 py-2 tabular-nums">{formatPercent(entry.max_relative_drop)}</td>
              <td className="px-3 py-2 tabular-nums">{levelsText(entry)}</td>
              <td className="px-3 py-2 tabular-nums">{formatPercent(entry.coverage)}</td>
              <td className="px-3 py-2">
                <Notes entry={entry} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** Thẻ: điện thoại (dưới md). */
function RankingCards({ ranking }: { ranking: AttackRankingEntry[] }) {
  return (
    <ol className="flex flex-col gap-3 md:hidden" aria-label="Bảng xếp hạng attack">
      {ranking.map((entry, i) => (
        <li
          key={entry.attack_spec_id}
          className="flex flex-col gap-1 rounded-xl border p-3 text-sm"
        >
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <span className="font-medium">
              {i + 1}. {entry.name}
            </span>
            <span className="text-muted-foreground">{ATTACK_KIND_LABEL[entry.kind]}</span>
          </div>
          <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-0.5">
            <dt className="text-muted-foreground">auc_drop</dt>
            <dd className="tabular-nums">{formatAuc(entry.auc_drop)}</dd>
            <dt className="text-muted-foreground">Mức sụt lớn nhất</dt>
            <dd className="tabular-nums">{formatPercent(entry.max_relative_drop)}</dd>
            <dt className="text-muted-foreground">Số level</dt>
            <dd className="tabular-nums">{levelsText(entry)}</dd>
            <dt className="text-muted-foreground">Độ phủ</dt>
            <dd className="tabular-nums">{formatPercent(entry.coverage)}</dd>
          </dl>
          {entry.partial && <Notes entry={entry} />}
        </li>
      ))}
    </ol>
  )
}

/**
 * Xếp hạng attack (requirements.md Phase 6, Frontend: tab Kết quả): thứ tự của backend (giảm dần
 * theo `auc_drop`, không đủ dữ liệu xếp cuối).
 */
export function AttackRanking({ ranking }: { ranking: AttackRankingEntry[] }) {
  if (ranking.length === 0) return null
  return (
    <section className="space-y-3" aria-labelledby="xep-hang-attack">
      <h3 id="xep-hang-attack" className="font-semibold">
        Xếp hạng attack
      </h3>
      <p className="text-sm text-muted-foreground">
        auc_drop: diện tích dưới đường mức sụt mAP@0.5 theo level chuẩn hóa (level / giá trị lớn
        nhất của tham số), tính đến độ phủ, không ngoại suy. Level bỏ qua do dừng sớm lấy mức sụt
        của level kích hoạt.
      </p>
      <AucChart ranking={ranking} />
      <RankingTable ranking={ranking} />
      <RankingCards ranking={ranking} />
    </section>
  )
}
