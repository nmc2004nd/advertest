import { useState } from 'react'
import { Link } from 'react-router'

import { formatDateTime } from '@/admin/format'
import { errorMessage } from '@/api/messages'
import { can } from '@/auth/permissions'
import { useMe } from '@/auth/useMe'
import { FormAlert } from '@/components/FormAlert'
import { LoadError } from '@/components/LoadError'
import { StatusBadge } from '@/components/status/StatusBadge'
import { Button } from '@/components/ui/button'
import type { ExperimentDetail, ReviewComment, RunView } from '@/contracts/api'
import { REPORT_STATUS_LABEL } from '@/features/reports/labels'

import { runLabel } from './format'
import { useAddComment, useComments } from './review-api'
import { DECISION_LABEL, MODEL_VERDICT_LABEL, OPEN_REVIEW } from './review-labels'

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="contents">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="min-w-0 break-words">{children}</dd>
    </div>
  )
}

function targetText(comment: ReviewComment, runs: RunView[]): string | null {
  if (comment.target_type === 'run') {
    const run = runs.find((r) => r.run_id === comment.target_id)
    return run ? `Run ${runLabel(run)}` : 'Run'
  }
  if (comment.target_type === 'failure_case') return 'Failure case'
  return null
}

/**
 * Tab Review của engineer (requirements.md Phase 8, Frontend engineer; plan task 26): trạng thái,
 * người nhận, quyết định, bình luận (chỉ thêm, khi đang chờ hoặc đang review).
 */
export function ReviewTab({ experiment, runs }: { experiment: ExperimentDetail; runs: RunView[] }) {
  const review = experiment.review
  const { data: me } = useMe()
  const comments = useComments(experiment.id, review !== null && review !== undefined)
  const add = useAddComment(experiment.id)
  const [body, setBody] = useState('')
  if (!review) {
    return <p className="text-sm text-muted-foreground">Experiment chưa gửi duyệt.</p>
  }
  const canComment = can(me, 'review.comment') && OPEN_REVIEW.includes(experiment.status)
  const send = () =>
    add.mutate(
      { target_type: 'experiment', target_id: experiment.id, body: body.trim() },
      { onSuccess: () => setBody('') },
    )

  return (
    <div className="space-y-6">
      <section className="space-y-2" aria-label="Trạng thái review">
        <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1 text-sm">
          <Row label="Trạng thái">
            <StatusBadge kind="experiment" status={experiment.status} />
          </Row>
          <Row label="Gửi duyệt">{formatDateTime(review.submitted_at)}</Row>
          <Row label="Người nhận">
            {review.assignee
              ? `${review.assignee.full_name}${review.claimed_at ? ` · ${formatDateTime(review.claimed_at)}` : ''}`
              : 'Chưa có reviewer nhận'}
          </Row>
          {review.submission_note && <Row label="Ghi chú">{review.submission_note}</Row>}
        </dl>
        {review.run_explanations.length > 0 && (
          <div className="text-sm">
            <p className="font-medium">Giải trình run</p>
            <ul className="list-disc space-y-1 pl-5">
              {review.run_explanations.map((e) => {
                const run = runs.find((r) => r.run_id === e.run_id)
                return (
                  <li key={e.run_id}>
                    {run ? runLabel(run) : e.run_id}: {e.text}
                  </li>
                )
              })}
            </ul>
          </div>
        )}
      </section>

      {review.decision && (
        <section
          className="space-y-2 rounded-lg border p-3 text-sm"
          aria-label="Quyết định"
          data-testid="quyet-dinh"
        >
          <p className="font-medium">
            Quyết định: {DECISION_LABEL[review.decision]}
            {review.decided_at && (
              <span className="font-normal text-muted-foreground">
                {' '}
                · {formatDateTime(review.decided_at)}
              </span>
            )}
          </p>
          {review.model_verdict && <p>{MODEL_VERDICT_LABEL[review.model_verdict]}</p>}
          {review.conclusion && <p>Kết luận: {review.conclusion}</p>}
          {review.mitigation && <p>Biện pháp khắc phục: {review.mitigation}</p>}
          {review.inconclusive_justification && (
            <p>Giải trình tiêu chí chưa kết luận: {review.inconclusive_justification}</p>
          )}
          {experiment.report && (
            // Phase 8 Group 6: report chính thức của experiment đã chấp nhận.
            <p data-testid="link-report">
              <Link to={`/reports/${experiment.report.id}`} className="font-medium underline">
                Report chính thức
              </Link>{' '}
              <span className="text-muted-foreground">
                ({REPORT_STATUS_LABEL[experiment.report.status]})
              </span>
            </p>
          )}
        </section>
      )}

      <section className="space-y-3" aria-label="Bình luận">
        <h2 className="font-medium">Bình luận ({review.comments_count})</h2>
        {comments.isError ? (
          <LoadError onRetry={() => void comments.refetch()} retrying={comments.isFetching} />
        ) : (
          <ul className="space-y-2">
            {(comments.data ?? []).map((c) => (
              <li key={c.id} className="rounded-lg bg-muted/50 p-3 text-sm">
                <p className="text-muted-foreground">
                  {c.author.full_name} · {formatDateTime(c.created_at)}
                  {targetText(c, runs) && ` · ${targetText(c, runs)}`}
                </p>
                <p className="whitespace-pre-wrap">{c.body}</p>
              </li>
            ))}
          </ul>
        )}
        {canComment && (
          <div className="flex flex-col gap-1.5">
            <label htmlFor="binh-luan-moi" className="text-sm font-medium">
              Thêm bình luận
            </label>
            <textarea
              id="binh-luan-moi"
              placeholder="Hỏi hoặc ghi chú cho người còn lại, ví dụ: case 000902 có phải do biển số bị làm mờ?"
              maxLength={4000}
              value={body}
              onChange={(event) => setBody(event.target.value)}
              className="min-h-20 w-full rounded-[14px] border border-line bg-field text-foreground outline-none backdrop-blur transition-[border-color,box-shadow] duration-200 placeholder:text-muted-foreground/70 hover:border-input focus-visible:border-cta/70 focus-visible:ring-4 focus-visible:ring-cta/15 px-3 py-2 text-base"
            />
            {add.isError && <FormAlert>{errorMessage(add.error)}</FormAlert>}
            <div>
              <Button onClick={send} disabled={!body.trim() || add.isPending}>
                {add.isPending ? 'Đang gửi…' : 'Gửi bình luận'}
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">Bình luận không sửa, không xóa được.</p>
          </div>
        )}
      </section>
    </div>
  )
}
