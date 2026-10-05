import { Check, CircleHelp, X } from 'lucide-react'
import { type ReactNode, useState } from 'react'
import { Link, useParams } from 'react-router'

import { errorMessage } from '@/api/messages'
import { can } from '@/auth/permissions'
import { useMe } from '@/auth/useMe'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { FormAlert } from '@/components/FormAlert'
import { LoadError } from '@/components/LoadError'
import { PageLoading } from '@/components/PageLoading'
import { StatusBadge } from '@/components/status/StatusBadge'
import { Button } from '@/components/ui/button'
import type {
  ExperimentDetail,
  ModelVerdict,
  RequiredCase,
  ReviewDecision,
  ReviewView,
} from '@/contracts/api'
import { useExperiment, useExperimentRuns } from '@/features/experiments/api'
import { DECISION_LABEL, MODEL_VERDICT_LABEL } from '@/features/experiments/review-labels'
import { ReviewTab } from '@/features/experiments/ReviewTab'
import { ResultsTab, RunsTable } from '@/features/experiments/tabs'
import { useProtocol } from '@/features/wizard/api'
import { COMPLIANCE_LABEL } from '@/features/wizard/protocol'

import { useClaim, useDecide, useRelease } from './api'
import {
  approveBlockers,
  CHECKLIST_LABEL,
  type DecisionForm,
  decisionBody,
  EMPTY_DECISION,
  criterionText,
  hasInconclusive,
  otherBlockers,
} from './decision'
import { KIND_LABEL, SEVERITY_LABEL } from './verdict'

const textareaClass =
  'min-h-20 w-full rounded-[14px] border border-line bg-field text-foreground outline-none backdrop-blur transition-[border-color,box-shadow] duration-200 placeholder:text-muted-foreground/70 hover:border-input focus-visible:border-cta/70 focus-visible:ring-4 focus-visible:ring-cta/15 px-3 py-2 text-base'

function Mark({ ok, unknown = false }: { ok: boolean; unknown?: boolean }) {
  if (unknown) {
    return <CircleHelp aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-threshold" />
  }
  return ok ? (
    <Check aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-emerald-600" />
  ) : (
    <X aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-destructive" />
  )
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-2" aria-label={title}>
      <h2 className="text-lg font-semibold">{title}</h2>
      {children}
    </section>
  )
}

const CRITERION_STATUS = {
  pass: 'Đạt',
  fail: 'Không đạt',
  inconclusive: 'Chưa kết luận',
} as const

function Criteria({ experiment, review }: { experiment: ExperimentDetail; review: ReviewView }) {
  const protocol = useProtocol(experiment.protocol.id)
  const criteria = protocol.data?.body.pass_criteria ?? []
  return (
    <ul className="space-y-1 text-sm" data-testid="ket-qua-tieu-chi">
      {review.criteria_results.map((r) => (
        <li key={r.index} className="flex gap-2">
          <Mark ok={r.status === 'pass'} unknown={r.status === 'inconclusive'} />
          <span>
            <span className="font-medium">{CRITERION_STATUS[r.status]}</span>
            {criteria[r.index]
              ? ` · ${criterionText(criteria[r.index])}`
              : ` · tiêu chí ${r.index + 1}`}
            <span className="block text-muted-foreground">{r.detail}</span>
          </span>
        </li>
      ))}
    </ul>
  )
}

function Compliance({ experiment }: { experiment: ExperimentDetail }) {
  const items = experiment.compliance ?? []
  if (items.length === 0) return <p className="text-sm text-muted-foreground">Không có.</p>
  return (
    <ul className="space-y-1 text-sm">
      {items.map((item, i) => (
        <li key={i} className="flex gap-2">
          <Mark ok={item.satisfied} />
          <span>
            {COMPLIANCE_LABEL[item.code]}
            {item.attack_spec_name ? ` (${item.attack_spec_name})` : ''}:{' '}
            <span className="text-muted-foreground">{item.detail}</span>
          </span>
        </li>
      ))}
    </ul>
  )
}

export function Checklist({ review }: { review: ReviewView }) {
  return (
    <ul className="space-y-1 text-sm" data-testid="danh-sach-kiem-tra">
      {review.checklist.map((item) => (
        <li key={item.code} className="flex gap-2">
          <Mark ok={item.satisfied} />
          <span>
            <span className="sr-only">{item.satisfied ? 'Đạt: ' : 'Chưa đạt: '}</span>
            {CHECKLIST_LABEL[item.code]}:{' '}
            <span className="text-muted-foreground">{item.detail}</span>
          </span>
        </li>
      ))}
    </ul>
  )
}

/** Case bắt buộc nhóm theo attack, kèm tiến độ "3/5 đã review". */
export function RequiredCases({
  experimentId,
  cases,
}: {
  experimentId: string
  cases: RequiredCase[]
}) {
  const groups = new Map<string, RequiredCase[]>()
  for (const c of cases)
    groups.set(c.attack_spec_name, [...(groups.get(c.attack_spec_name) ?? []), c])
  if (cases.length === 0)
    return <p className="text-sm text-muted-foreground">Không có case bắt buộc.</p>
  return (
    <div className="space-y-3">
      {[...groups].map(([name, list]) => {
        const done = list.filter((c) => c.current_verdict).length
        return (
          <div key={name} className="space-y-1">
            <p className="font-medium">
              {name}{' '}
              <span className="text-sm font-normal text-muted-foreground">
                {done}/{list.length} đã review
              </span>
            </p>
            <ul className="grid gap-2 md:grid-cols-2">
              {list.map((c) => (
                <li key={c.failure_case_id}>
                  <Link
                    to={`/reviews/${experimentId}/cases/${c.failure_case_id}`}
                    className="flex min-h-11 flex-col rounded-lg border p-3 text-sm hover:bg-muted"
                  >
                    <span>
                      Ảnh {c.image_id} · level {c.level} · điểm {c.severity_score}
                    </span>
                    <span className="text-muted-foreground">
                      {c.current_verdict
                        ? `v${c.current_verdict.version}: ${SEVERITY_LABEL[c.current_verdict.severity]}, ${KIND_LABEL[c.current_verdict.kind]}`
                        : 'Chưa có verdict'}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        )
      })}
    </div>
  )
}

/** Khung quyết định: "Chấp nhận" khóa tới khi đủ điều kiện, kèm lý do. */
export function DecisionPanel({
  experiment,
  review,
  initial = EMPTY_DECISION,
}: {
  experiment: ExperimentDetail
  review: ReviewView
  initial?: DecisionForm
}) {
  const decide = useDecide(experiment.id)
  const [form, setForm] = useState<DecisionForm>(initial)
  const [confirm, setConfirm] = useState<ReviewDecision | null>(null)
  const blockers = approveBlockers(review, form)
  const others = otherBlockers(form)
  const patch = (value: Partial<DecisionForm>) => setForm((f) => ({ ...f, ...value }))
  const field = (
    id: string,
    label: string,
    value: string,
    key: keyof DecisionForm,
    hint?: string,
    placeholder?: string,
  ) => (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium">
        {label}
      </label>
      <textarea
        id={id}
        maxLength={4000}
        value={value}
        placeholder={placeholder}
        onChange={(event) => patch({ [key]: event.target.value })}
        className={textareaClass}
      />
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  )
  return (
    <div className="space-y-3 rounded-xl border p-4" data-testid="khung-quyet-dinh">
      {field(
        'ket-luan',
        'Kết luận',
        form.conclusion,
        'conclusion',
        'Với yêu cầu sửa và từ chối: lý do.',
        'Ví dụ: Model sụt 60% mAP ở FGSM eps 8, vượt ngưỡng 30% của protocol KITTI v1.',
      )}
      {field(
        'khac-phuc',
        'Biện pháp khắc phục',
        form.mitigation,
        'mitigation',
        undefined,
        'Ví dụ: Huấn luyện đối kháng với PGD eps 4, chạy lại trước đợt thử nghiệm.',
      )}
      <div className="flex flex-col gap-1.5">
        <label htmlFor="ket-luan-model" className="text-sm font-medium">
          Kết luận về model
        </label>
        <select
          id="ket-luan-model"
          value={form.modelVerdict}
          onChange={(event) => patch({ modelVerdict: event.target.value as ModelVerdict | '' })}
          className="min-h-11 rounded-[14px] border border-line bg-field text-foreground outline-none backdrop-blur transition-[border-color,box-shadow] duration-200 placeholder:text-muted-foreground/70 hover:border-input focus-visible:border-cta/70 focus-visible:ring-4 focus-visible:ring-cta/15 px-3 text-base"
        >
          <option value="">Chọn kết luận về model…</option>
          {(Object.keys(MODEL_VERDICT_LABEL) as ModelVerdict[]).map((v) => (
            <option key={v} value={v}>
              {MODEL_VERDICT_LABEL[v]}
            </option>
          ))}
        </select>
        <p className="text-xs text-muted-foreground">
          Chấp nhận là chấp nhận bài test; kết luận về model có thể là không đạt.
        </p>
      </div>
      {hasInconclusive(review) &&
        field(
          'giai-trinh-tieu-chi',
          'Giải trình tiêu chí chưa kết luận',
          form.inconclusiveJustification,
          'inconclusiveJustification',
          undefined,
          'Vì sao chấp nhận dù tiêu chí chưa kết luận được, ví dụ: thiếu dữ liệu ban đêm.',
        )}
      {decide.isError && <FormAlert>{errorMessage(decide.error)}</FormAlert>}
      <div className="flex flex-col gap-2 md:flex-row">
        <Button disabled={blockers.length > 0} onClick={() => setConfirm('approve')}>
          Chấp nhận
        </Button>
        <Button
          variant="outline"
          disabled={others.length > 0}
          onClick={() => setConfirm('changes_requested')}
        >
          Yêu cầu sửa
        </Button>
        <Button
          variant="destructive"
          disabled={others.length > 0}
          onClick={() => setConfirm('reject')}
        >
          Từ chối
        </Button>
      </div>
      {blockers.length > 0 && (
        <div className="text-sm" data-testid="ly-do-khoa">
          <p className="font-medium">Chưa chấp nhận được:</p>
          <ul className="list-disc pl-5 text-muted-foreground">
            {blockers.map((b) => (
              <li key={b}>{b}</li>
            ))}
          </ul>
        </div>
      )}
      <ConfirmDialog
        open={confirm !== null}
        onOpenChange={(open) => !open && setConfirm(null)}
        title={confirm ? `${DECISION_LABEL[confirm]}?` : ''}
        description="Quyết định là trạng thái cuối: không thêm verdict, bình luận hay giải trình được nữa."
        confirmLabel={confirm ? DECISION_LABEL[confirm] : ''}
        destructive={confirm === 'reject'}
        pending={decide.isPending}
        onConfirm={() =>
          confirm &&
          decide.mutate(decisionBody(confirm, form), { onSettled: () => setConfirm(null) })
        }
      >
        <div className="space-y-1 text-sm">
          <p>{experiment.name}</p>
          {confirm === 'approve' && form.modelVerdict && (
            <p>{MODEL_VERDICT_LABEL[form.modelVerdict]}. Report chính thức sẽ được sinh.</p>
          )}
        </div>
      </ConfirmDialog>
    </div>
  )
}

/** Không gian review một experiment (requirements.md Phase 8, Frontend reviewer; plan task 28). */
export function ReviewPage() {
  const { id = '' } = useParams()
  const { data: me } = useMe()
  const experiment = useExperiment(id)
  const runs = useExperimentRuns(id, experiment.data?.status)
  const claim = useClaim(id)
  const release = useRelease(id)
  if (experiment.isPending) return <PageLoading />
  if (experiment.isError) {
    return (
      <div className="p-4 md:p-6">
        <LoadError onRetry={() => void experiment.refetch()} retrying={experiment.isFetching} />
      </div>
    )
  }
  const e = experiment.data
  const review = e.review
  const runList = runs.data ?? []
  const isOwner = me?.id === e.owner.id
  const reviewer = can(me, 'review.decide')
  const mine = review?.assignee?.id === me?.id && e.status === 'in_review'
  const action = claim.isError ? claim.error : release.isError ? release.error : null

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6 p-4 md:p-6">
      <header className="flex flex-col gap-2">
        <Link to="/reviews" className="text-sm text-muted-foreground hover:underline">
          ← Hàng đợi review
        </Link>
        <div className="flex flex-wrap items-start justify-between gap-2">
          <h1 className="min-w-0 text-2xl font-semibold break-all">{e.name}</h1>
          <div className="flex flex-wrap gap-2">
            {reviewer && !isOwner && e.status === 'submitted_for_review' && (
              <Button onClick={() => claim.mutate(undefined)} disabled={claim.isPending}>
                Nhận review
              </Button>
            )}
            {mine && (
              <Button
                variant="outline"
                onClick={() => release.mutate(undefined)}
                disabled={release.isPending}
              >
                Trả lại
              </Button>
            )}
          </div>
        </div>
        <p className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          <StatusBadge kind="experiment" status={e.status} />
          {e.owner.full_name} · {e.protocol.name} · {e.model.name} · {e.slice.name}
        </p>
        <Link to={`/experiments/${e.id}`} className="text-sm hover:underline">
          Xem experiment
        </Link>
      </header>
      {isOwner && (
        <FormAlert>
          Đây là experiment của bạn: bạn không được review experiment do mình tạo.
        </FormAlert>
      )}
      {action && <FormAlert>{errorMessage(action)}</FormAlert>}
      {!review ? (
        <p className="text-muted-foreground">Experiment chưa gửi duyệt.</p>
      ) : (
        <>
          <div className="grid gap-6 lg:grid-cols-2">
            <Section title="Tuân thủ protocol">
              <Compliance experiment={e} />
            </Section>
            <Section title="Kết quả tiêu chí (tham khảo)">
              <Criteria experiment={e} review={review} />
            </Section>
          </div>
          <Section title="Danh sách kiểm tra trước khi chấp nhận">
            <Checklist review={review} />
          </Section>
          <Section title="Case bắt buộc">
            <RequiredCases experimentId={e.id} cases={review.required_cases} />
          </Section>
          <Section title="Run">
            <RunsTable runs={runList} />
          </Section>
          <Section title="Kết quả">
            <ResultsTab experiment={e} runs={runList} />
          </Section>
          <Section title="Gửi duyệt, quyết định và bình luận">
            <ReviewTab experiment={e} runs={runList} />
          </Section>
          {mine && (
            <Section title="Quyết định">
              <DecisionPanel experiment={e} review={review} />
            </Section>
          )}
        </>
      )}
    </div>
  )
}
