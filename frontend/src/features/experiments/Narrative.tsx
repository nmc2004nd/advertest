import { Loader2, RefreshCw, Sparkles, TriangleAlert } from 'lucide-react'
import { useId } from 'react'

import { errorMessage } from '@/api/messages'
import { formatDateTime } from '@/admin/format'
import { Button } from '@/components/ui/button'
import type { ExperimentDetail, ExperimentNarrative } from '@/contracts/api'
import { NARRATIVE } from '@/copy/narrative'

import { useCreateNarrative, useNarrative } from './api'

function NarrativeBody({ narrative, id }: { narrative: ExperimentNarrative; id: string }) {
  return (
    <div className="space-y-4" data-testid="narrative">
      <p className="text-[15px] leading-6">{narrative.summary}</p>
      {narrative.findings.length > 0 && (
        <div className="space-y-2">
          <h4 id={`${id}-phan-tich`} className="text-sm font-semibold">
            {NARRATIVE.findings}
          </h4>
          <ul aria-labelledby={`${id}-phan-tich`} className="grid gap-2 lg:grid-cols-2">
            {narrative.findings.map((finding, i) => (
              <li
                key={`${i}-${finding.title}`}
                className="rounded-xl border border-line bg-surface-solid px-4 py-3"
              >
                <p className="font-medium">{finding.title}</p>
                <p className="mt-1 text-sm leading-6 text-muted-foreground">{finding.detail}</p>
              </li>
            ))}
          </ul>
        </div>
      )}
      {narrative.next_steps.length > 0 && (
        <div className="space-y-2">
          <h4 id={`${id}-goi-y`} className="text-sm font-semibold">
            {NARRATIVE.nextSteps}
          </h4>
          <ul aria-labelledby={`${id}-goi-y`} className="space-y-1.5 text-sm leading-6">
            {narrative.next_steps.map((step, i) => (
              <li key={`${i}-${step}`} className="flex gap-2">
                <span
                  aria-hidden="true"
                  className="mt-2.5 size-1 shrink-0 rounded-full bg-current"
                />
                {step}
              </li>
            ))}
          </ul>
        </div>
      )}
      <p className="text-xs text-muted-foreground">
        {NARRATIVE.meta(narrative.llm_model, formatDateTime(narrative.created_at))}
      </p>
    </div>
  )
}

/**
 * Mục "Nhận xét chi tiết" của tab Kết quả: LLM (DeepSeek) viết từ số liệu insight khi người dùng
 * bấm; server lưu theo dữ liệu đầu vào nên xem lại không gọi LLM. Ẩn khi server chưa cấu hình LLM
 * hoặc không đọc được trạng thái. Không dùng cho thử nhanh và không có trong report.
 */
export function NarrativeSection({ experiment }: { experiment: ExperimentDetail }) {
  const id = useId()
  const state = useNarrative(experiment.id, experiment.status)
  const create = useCreateNarrative(experiment.id)
  if (!state.data?.enabled) return null
  const { narrative, stale, can_generate } = state.data
  const showButton = can_generate && (narrative === null || stale)

  return (
    <section
      className="panel space-y-4 p-5"
      aria-labelledby={`${id}-nhan-xet`}
      aria-busy={create.isPending || undefined}
    >
      <div className="space-y-1.5">
        <div className="flex flex-wrap items-center gap-2">
          <Sparkles aria-hidden="true" className="size-4 text-muted-foreground" />
          <h3 id={`${id}-nhan-xet`} className="font-semibold">
            {NARRATIVE.title}
          </h3>
          <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-semibold text-muted-foreground">
            {NARRATIVE.badge}
          </span>
          {narrative?.partial && (
            <span className="rounded-full bg-threshold/12 px-2 py-0.5 text-xs font-semibold text-threshold">
              {NARRATIVE.partial}
            </span>
          )}
        </div>
        <p className="max-w-[72ch] text-sm text-muted-foreground">{NARRATIVE.disclaimer}</p>
      </div>

      {stale && (
        <p
          role="status"
          className="flex max-w-[72ch] gap-2 rounded-lg border border-threshold/40 bg-threshold/8 px-3 py-2 text-sm"
        >
          <TriangleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-threshold" />
          {NARRATIVE.stale}
        </p>
      )}

      {narrative ? (
        <NarrativeBody narrative={narrative} id={id} />
      ) : (
        <p className="max-w-[72ch] text-sm leading-6">
          {can_generate ? NARRATIVE.intro : NARRATIVE.waiting}
        </p>
      )}

      {showButton && (
        <div className="flex flex-wrap items-center gap-3">
          <Button type="button" onClick={() => create.mutate()} disabled={create.isPending}>
            {create.isPending ? (
              <Loader2 aria-hidden="true" className="animate-spin motion-reduce:animate-none" />
            ) : narrative ? (
              <RefreshCw aria-hidden="true" />
            ) : (
              <Sparkles aria-hidden="true" />
            )}
            {narrative ? NARRATIVE.recreate : NARRATIVE.create}
          </Button>
          {create.isPending && (
            <span role="status" className="text-sm text-muted-foreground">
              {NARRATIVE.creating}
            </span>
          )}
        </div>
      )}
      {create.isError && (
        <p role="alert" className="text-sm text-destructive">
          {errorMessage(create.error)}
        </p>
      )}
    </section>
  )
}
