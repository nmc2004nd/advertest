import type { RobustnessRow } from '@/contracts/api'
import { NOT_RUN, READING } from '@/copy/charts'
import { cn } from '@/lib/utils'

import { ChartReading } from './ChartReading'
import {
  bandLabel,
  type DropTone,
  dropTone,
  matrixSentence,
  percent,
  WEAKNESS_DROP,
} from './sentences'

/** Nền ô theo thang màu của design.md mục 3 (`--fail` 20/50/85%, ô chưa chạy gạch chéo `--line`). */
const TONE_CLASS: Record<DropTone, string> = {
  empty:
    'bg-[repeating-linear-gradient(-45deg,var(--line)_0_6px,transparent_6px_12px)] text-muted-foreground',
  none: 'bg-surface-solid',
  low: 'bg-fail/20',
  mid: 'bg-fail/50',
  high: 'bg-fail/85 text-white',
}

const LEGEND: { tone: DropTone; label: string }[] = [
  { tone: 'none', label: '< 10%' },
  { tone: 'low', label: '10–30%' },
  { tone: 'mid', label: '30–50%' },
  { tone: 'high', label: '≥ 50%' },
  { tone: 'empty', label: NOT_RUN },
]

function Swatch({ tone, strong = false }: { tone: DropTone; strong?: boolean }) {
  return (
    <span
      aria-hidden
      className={cn(
        'inline-block size-4 shrink-0 rounded-sm border border-line',
        TONE_CLASS[tone],
        strong && 'border-2 border-fail',
      )}
    />
  )
}

/** Chú thích thang màu cạnh ma trận (luôn hiện). */
export function MatrixLegend() {
  return (
    <div data-testid="matrix-legend" className="space-y-2 text-xs">
      <p className="font-semibold text-muted-foreground">Mức sụt lớn nhất trong dải</p>
      <ul className="flex flex-wrap gap-x-4 gap-y-1.5 lg:flex-col">
        {LEGEND.map(({ tone, label }) => (
          <li key={tone} className="flex items-center gap-2">
            <Swatch tone={tone} />
            {label}
          </li>
        ))}
        <li className="flex items-center gap-2">
          <Swatch tone="none" strong />
          Viền đỏ: từ {percent(WEAKNESS_DROP)} trở lên
        </li>
      </ul>
    </div>
  )
}

/**
 * Ma trận độ bền (requirements.md Phase R3, Kết quả và insight): hàng là attack quét lưới, 4 cột là
 * dải cường độ; ô ghi số phần trăm và tô theo thang màu; ô `null` ghi "Chưa chạy".
 */
export function RobustnessMatrix({
  rows,
  bands,
  name = (row) => row.attack_name,
}: {
  rows: RobustnessRow[]
  bands: readonly (readonly [number, number])[]
  /** Tên hiển thị của attack (metadata), mặc định tên kỹ thuật. */
  name?: (row: RobustnessRow) => string
}) {
  return (
    <section className="space-y-3" aria-labelledby="ma-tran-do-ben">
      <h3 id="ma-tran-do-ben" className="font-semibold">
        Ma trận độ bền
      </h3>
      <ChartReading sentence={matrixSentence(rows, bands, name)} reading={READING.matrix} />
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_auto]">
        <div className="overflow-x-auto">
          <table
            data-testid="robustness-matrix"
            className="w-full min-w-[20rem] table-fixed border-separate border-spacing-1 text-sm"
          >
            <caption className="sr-only">
              Mức sụt mAP@0.5 tương đối lớn nhất theo attack và dải cường độ
            </caption>
            <thead>
              <tr>
                <th
                  scope="col"
                  className="w-[28%] px-1 text-left text-xs font-semibold text-muted-foreground"
                >
                  Attack
                </th>
                {bands.map((band) => (
                  <th
                    key={band[0]}
                    scope="col"
                    className="px-1 text-center text-xs font-semibold text-muted-foreground"
                  >
                    {bandLabel(band)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.attack_spec_id}>
                  <th scope="row" className="truncate px-1 text-left font-medium" title={name(row)}>
                    {name(row)}
                  </th>
                  {row.cells.map((cell) => {
                    const drop = cell.max_relative_drop
                    const tone = dropTone(drop)
                    return (
                      <td
                        key={cell.band}
                        data-testid="matrix-cell"
                        data-band={cell.band}
                        data-tone={tone}
                        className={cn(
                          'h-11 rounded-md border border-line px-1 text-center tabular-nums',
                          TONE_CLASS[tone],
                          drop !== null && drop >= WEAKNESS_DROP && 'border-2 border-fail',
                        )}
                      >
                        {drop === null ? <span className="text-xs">{NOT_RUN}</span> : percent(drop)}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <MatrixLegend />
      </div>
    </section>
  )
}
