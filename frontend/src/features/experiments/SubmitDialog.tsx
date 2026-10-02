import { Check, X } from 'lucide-react'
import { useState } from 'react'

import { ApiError } from '@/api/errors'
import { errorMessage } from '@/api/messages'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { FormAlert } from '@/components/FormAlert'
import type { ExperimentDetail, RunView } from '@/contracts/api'

import { runLabel } from './format'
import { useSubmitForReview } from './review-api'
import { canSubmit, SUBMIT_CHECK_LABEL } from './review-labels'

const textareaClass =
  'min-h-20 w-full rounded-lg border border-input bg-background px-3 py-2 text-base aria-invalid:border-destructive'

/**
 * Hộp gửi duyệt (requirements.md Phase 8, Frontend engineer; plan task 25): danh sách điều kiện,
 * ghi chú, lời giải trình cho từng run bắt buộc chưa hoàn thành. Gửi duyệt không hoàn tác được:
 * experiment bị khóa.
 */
export function SubmitDialog({
  experiment,
  runs,
  open,
  onOpenChange,
}: {
  experiment: ExperimentDetail
  runs: RunView[]
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const submit = useSubmitForReview(experiment.id)
  const [note, setNote] = useState('')
  const [explanations, setExplanations] = useState<Record<string, string>>({})
  const needed = experiment.runs_requiring_explanation ?? []
  const fieldErrors =
    submit.error instanceof ApiError
      ? Object.fromEntries(submit.error.fields.map((f) => [f.path, f.message]))
      : {}
  const missing = needed.filter((id) => !(explanations[id] ?? '').trim())
  const ready = canSubmit(experiment) && missing.length === 0

  const send = () =>
    submit.mutate(
      {
        note: note.trim() || null,
        run_explanations: Object.fromEntries(needed.map((id) => [id, explanations[id].trim()])),
      },
      { onSuccess: () => onOpenChange(false) },
    )

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Gửi duyệt experiment?"
      description="Sau khi gửi, experiment bị khóa: không hủy, không sửa, không chạy thêm được; chỉ còn bình luận."
      confirmLabel="Gửi duyệt"
      pending={submit.isPending}
      canConfirm={ready}
      onConfirm={send}
    >
      <SubmitFields
        experiment={experiment}
        runs={runs}
        note={note}
        onNote={setNote}
        explanations={explanations}
        onExplanation={(runId, text) =>
          setExplanations((current) => ({ ...current, [runId]: text }))
        }
        fieldErrors={fieldErrors}
        error={submit.isError ? errorMessage(submit.error) : null}
      />
    </ConfirmDialog>
  )
}

/** Thân hộp gửi duyệt: điều kiện ✓/✗, giải trình từng run, ghi chú. */
export function SubmitFields({
  experiment,
  runs,
  note,
  onNote,
  explanations,
  onExplanation,
  fieldErrors,
  error,
}: {
  experiment: ExperimentDetail
  runs: RunView[]
  note: string
  onNote: (note: string) => void
  explanations: Record<string, string>
  onExplanation: (runId: string, text: string) => void
  fieldErrors: Record<string, string>
  error: string | null
}) {
  const needed = experiment.runs_requiring_explanation ?? []
  const missing = needed.filter((id) => !(explanations[id] ?? '').trim())
  return (
    <div className="max-h-[60vh] space-y-4 overflow-y-auto text-sm">
      {error && Object.keys(fieldErrors).length === 0 && <FormAlert>{error}</FormAlert>}
      <section className="space-y-1" aria-label="Điều kiện gửi duyệt">
        <p className="font-medium">Điều kiện</p>
        <ul className="space-y-1" data-testid="dieu-kien-gui-duyet">
          {(experiment.submit_check ?? []).map((item) => (
            <li key={item.code} className="flex gap-2">
              {item.satisfied ? (
                <Check aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-emerald-600" />
              ) : (
                <X aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-destructive" />
              )}
              <span>
                <span className="sr-only">{item.satisfied ? 'Đạt: ' : 'Chưa đạt: '}</span>
                {SUBMIT_CHECK_LABEL[item.code]}:{' '}
                <span className="text-muted-foreground">{item.detail}</span>
              </span>
            </li>
          ))}
        </ul>
      </section>
      {needed.length > 0 && (
        <section className="space-y-3" aria-label="Giải trình run">
          <p className="font-medium">
            Giải trình cho run bắt buộc chưa hoàn thành ({needed.length - missing.length}/
            {needed.length})
          </p>
          {needed.map((runId) => {
            const run = runs.find((r) => r.run_id === runId)
            const id = `giai-trinh-${runId}`
            const error = fieldErrors[`run_explanations.${runId}`]
            return (
              <div key={runId} className="flex flex-col gap-1.5">
                <label htmlFor={id} className="font-medium">
                  {run ? runLabel(run) : runId}
                  {run && <span className="text-muted-foreground"> · {run.status}</span>}
                </label>
                <textarea
                  id={id}
                  maxLength={4000}
                  value={explanations[runId] ?? ''}
                  aria-invalid={error ? true : undefined}
                  onChange={(event) => onExplanation(runId, event.target.value)}
                  className={textareaClass}
                />
                {error && (
                  <p role="alert" className="text-destructive">
                    {error}
                  </p>
                )}
              </div>
            )
          })}
        </section>
      )}
      <div className="flex flex-col gap-1.5">
        <label htmlFor="ghi-chu-gui-duyet" className="font-medium">
          Ghi chú cho reviewer (không bắt buộc)
        </label>
        <textarea
          id="ghi-chu-gui-duyet"
          maxLength={4000}
          value={note}
          onChange={(event) => onNote(event.target.value)}
          className={textareaClass}
        />
      </div>
    </div>
  )
}
