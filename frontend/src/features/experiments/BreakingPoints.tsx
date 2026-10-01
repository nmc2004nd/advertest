import { ChevronRight } from 'lucide-react'
import { useState } from 'react'

import { BreakpointCard } from '@/components/charts/BreakpointCard'
import { BreakpointComparison } from '@/components/charts/BreakpointComparison'
import { attackName, searchAttacks, specInfoMap } from '@/components/charts/breakpoints'
import { SearchTrajectory } from '@/components/charts/SearchTrajectory'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import type { ExperimentDetail, RunView } from '@/contracts/api'

import { useAttackCatalog } from './api'

/**
 * Mục "Điểm gãy" của tab Kết quả (requirements.md Phase 7, Frontend). Từ md: thẻ tóm tắt, biểu đồ
 * so sánh, quỹ đạo từng attack. Điện thoại: chỉ thẻ; chạm thẻ mở quỹ đạo toàn màn hình.
 */
export function BreakingPoints({
  experiment,
  runs,
}: {
  experiment: ExperimentDetail
  runs: RunView[]
}) {
  const catalog = useAttackCatalog()
  const [openId, setOpenId] = useState<string | null>(null)
  const attacks = searchAttacks(experiment, specInfoMap(runs, catalog.data ?? []))
  if (attacks.length === 0) return null
  const open = attacks.find((a) => a.attackSpecId === openId)
  return (
    <section className="space-y-4" aria-labelledby="diem-gay">
      <h3 id="diem-gay" className="font-semibold">
        Điểm gãy
      </h3>
      <ul className="grid gap-3 md:grid-cols-2">
        {attacks.map((attack) => (
          <li
            key={attack.attackSpecId}
            className="relative flex min-w-0 items-center gap-2 rounded-xl border p-3"
          >
            <BreakpointCard attack={attack} />
            {attack.result && (
              <>
                <ChevronRight
                  aria-hidden="true"
                  className="size-4 shrink-0 text-muted-foreground md:hidden"
                />
                {/* Điện thoại: nút phủ cả thẻ (chạm thẻ để mở quỹ đạo toàn màn hình). */}
                <button
                  type="button"
                  onClick={() => setOpenId(attack.attackSpecId)}
                  aria-label={`Mở quỹ đạo của ${attackName(attack)}`}
                  className="absolute inset-0 rounded-xl hover:bg-muted/40 focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none md:hidden"
                />
              </>
            )}
          </li>
        ))}
      </ul>
      <div className="hidden space-y-6 md:block" data-testid="diem-gay-chi-tiet">
        <BreakpointComparison attacks={attacks} />
        {attacks
          .filter((attack) => attack.result)
          .map((attack) => (
            <section
              key={attack.attackSpecId}
              className="space-y-2 rounded-lg border p-3 md:p-4"
              aria-label={attackName(attack)}
            >
              <h4 className="font-semibold">{attackName(attack)}</h4>
              <SearchTrajectory attack={attack} />
            </section>
          ))}
      </div>
      <Dialog open={open !== undefined} onOpenChange={(value) => !value && setOpenId(null)}>
        {open && (
          <DialogContent className="inset-0 h-dvh max-h-none rounded-none md:h-auto md:max-h-[90dvh] md:max-w-3xl md:rounded-xl">
            <DialogTitle>{attackName(open)}</DialogTitle>
            <DialogDescription>Quỹ đạo tìm ngưỡng và số liệu từng điểm.</DialogDescription>
            <BreakpointCard attack={open} />
            <SearchTrajectory attack={open} />
          </DialogContent>
        )}
      </Dialog>
    </section>
  )
}
