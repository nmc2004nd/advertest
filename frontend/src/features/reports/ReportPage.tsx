import { FileDown, ShieldCheck } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link, useParams } from 'react-router'

import { formatDateTime } from '@/admin/format'
import { errorMessage } from '@/api/messages'
import { can } from '@/auth/permissions'
import { useMe } from '@/auth/useMe'
import { AttackRanking } from '@/components/charts/AttackRanking'
import { THRESHOLD_KIND_LABEL } from '@/components/charts/breakpoints'
import { FormAlert } from '@/components/FormAlert'
import { LoadError } from '@/components/LoadError'
import { PageLoading } from '@/components/PageLoading'
import { StatusBadge } from '@/components/status/StatusBadge'
import { Button } from '@/components/ui/button'
import type { ReportDownload, ReportSnapshot, ReportView } from '@/contracts/api'
import { artifactSrc } from '@/features/experiments/api'
import { formatDuration } from '@/features/experiments/format'
import { MODEL_VERDICT_LABEL } from '@/features/experiments/review-labels'
import { criterionText } from '@/features/reviews/decision'
import { KIND_LABEL, SEVERITY_LABEL } from '@/features/reviews/verdict'

import { useDownloadReport, useRegenerateReport, useReport } from './api'
import {
  decimal,
  OFFICIAL,
  percent,
  REPORT_STATUS_LABEL,
  SCOPE_LABEL,
  TIMELINE_LABEL,
} from './labels'

function Section({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return (
    <section className="space-y-3" aria-labelledby={`muc-${n}`}>
      <h2 id={`muc-${n}`} className="text-lg font-semibold">
        {n}. {title}
      </h2>
      {children}
    </section>
  )
}

/** Bảng cuộn ngang trong khung riêng: trang không cuộn ngang ở 390px. */
function Table({
  caption,
  head,
  children,
}: {
  caption: string
  head: string[]
  children: ReactNode
}) {
  return (
    <div className="overflow-x-auto rounded-xl border border-border">
      <table className="w-full text-left text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead className="bg-muted/50">
          <tr>
            {head.map((h) => (
              <th key={h} scope="col" className="px-3 py-2 font-medium whitespace-nowrap">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  )
}

const td = 'border-t border-border px-3 py-2 align-top'

function Hash({ value }: { value: string | null | undefined }) {
  return <span className="font-mono text-xs break-all">{value ?? '—'}</span>
}

function Fields({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl className="grid gap-x-4 gap-y-2 text-sm md:grid-cols-[minmax(10rem,auto)_1fr]">
      {rows.map(([label, value]) => (
        <div key={label} className="contents">
          <dt className="text-muted-foreground">{label}</dt>
          <dd className="min-w-0">{value}</dd>
        </div>
      ))}
    </dl>
  )
}

/** Nội dung snapshot đã lưu, đủ 9 mục như PDF (requirements.md Phase 8, mục Report). */
export function SnapshotView({ snapshot }: { snapshot: ReportSnapshot }) {
  const { summary, configuration: config, results, history } = snapshot
  const criteria = config.protocol.body.pass_criteria
  const specName = (id: string) => config.attack_specs.find((s) => s.id === id)?.name ?? id
  return (
    <div className="flex flex-col gap-8">
      <Section n={1} title="Tóm tắt">
        <Fields
          rows={[
            [
              'Kết luận về model',
              <strong key="v">{MODEL_VERDICT_LABEL[summary.model_verdict]}</strong>,
            ],
            ['Kết luận', summary.conclusion],
            ['Biện pháp khắc phục', summary.mitigation],
            ...(summary.inconclusive_justification
              ? ([['Giải trình tiêu chí chưa kết luận', summary.inconclusive_justification]] as [
                  string,
                  ReactNode,
                ][])
              : []),
            ['Người tạo', summary.owner.full_name],
            [
              'Người duyệt',
              `${summary.approved_by.full_name}, ${formatDateTime(summary.approved_at)}`,
            ],
          ]}
        />
        <p className="text-sm text-muted-foreground">
          Chấp nhận review là chấp nhận bài test làm đúng quy trình, không phải tuyên bố model đạt.
        </p>
      </Section>

      <Section n={2} title="Phạm vi và lưu ý bắt buộc">
        <ul className="list-disc space-y-1 pl-5 text-sm">
          {snapshot.notes.map((note) => (
            <li key={note.code}>{note.text}</li>
          ))}
        </ul>
      </Section>

      <Section n={3} title="Cấu hình">
        <Fields
          rows={[
            [
              'Protocol',
              <span key="p">
                {config.protocol.name} v{config.protocol.version} ·{' '}
                <Hash value={config.protocol.body_sha256} />
              </span>,
            ],
            [
              'Model',
              <span key="m">
                {config.model.name} · <Hash value={config.model.weights_sha256} />
              </span>,
            ],
            [
              'Dataset version',
              <span key="d">
                {config.dataset_version.dataset_name}
                {config.dataset_version.anonymized ? ' (đã làm mờ)' : ''} ·{' '}
                <Hash value={config.dataset_version.manifest_sha256} />
              </span>,
            ],
            [
              'Slice',
              <span key="s">
                {config.slice.name}, {config.slice.size} ảnh ·{' '}
                <Hash value={config.slice.slice_sha256} />
              </span>,
            ],
            [
              'Class mapping',
              <span key="c">
                <Hash value={config.class_mapping.mapping_sha256} />
                {config.class_mapping.excluded_classes.length > 0 &&
                  ` · loại: ${config.class_mapping.excluded_classes.join(', ')}`}
              </span>,
            ],
            [
              'Compute target',
              `${config.compute_target.name}${config.gpu_model ? ` · ${config.gpu_model}` : ''}`,
            ],
            ['Hash cấu hình', <Hash key="h" value={config.config_sha256} />],
          ]}
        />
        <Table caption="Attack spec" head={['Attack', 'Version', 'Bắt buộc', 'Hash']}>
          {config.attack_specs.map((s) => (
            <tr key={s.id}>
              <td className={td}>{s.name}</td>
              <td className={td}>v{s.version}</td>
              <td className={td}>{s.required ? 'Có' : 'Không'}</td>
              <td className={td}>
                <Hash value={s.spec_sha256} />
              </td>
            </tr>
          ))}
        </Table>
      </Section>

      <Section n={4} title="Kết quả">
        {results.clean_metrics && (
          <p className="text-sm">
            Metric sạch: mAP50 {decimal(results.clean_metrics.map50)}, mAP50-95{' '}
            {decimal(results.clean_metrics.map50_95)}
          </p>
        )}
        {results.grid.map((attack) => (
          <Table
            key={attack.attack_spec_id}
            caption={`Quét lưới ${attack.attack_spec_name}`}
            head={[
              `${attack.attack_spec_name}: level`,
              'Trạng thái',
              'mAP50',
              'Mức sụt tương đối',
              'Tỷ lệ tấn công thành công',
            ]}
          >
            {attack.points.map((p) => (
              <tr key={p.run_id}>
                <td className={td}>{p.level}</td>
                <td className={td}>
                  <StatusBadge kind="run" status={p.status} />
                  {p.early_stop_from_run_id && (
                    <span className="block text-xs text-muted-foreground">suy từ dừng sớm</span>
                  )}
                </td>
                <td className={td}>{decimal(p.map50)}</td>
                <td className={td}>{percent(p.relative_drop)}</td>
                <td className={td}>{percent(p.attack_success_rate)}</td>
              </tr>
            ))}
          </Table>
        ))}
        {results.attack_ranking.length > 0 && <AttackRanking ranking={results.attack_ranking} />}
        {results.searches.length > 0 && (
          <ul className="space-y-2 text-sm">
            {results.searches.map((s) => (
              <li key={s.attack_spec_id} className="rounded-lg border p-3">
                <p className="font-medium">
                  {specName(s.attack_spec_id)}: tìm ngưỡng {THRESHOLD_KIND_LABEL[s.threshold_kind]}{' '}
                  {percent(s.threshold)}
                </p>
                <p>
                  Điểm gãy {s.breaking_point ?? '—'}
                  {s.bracket && ` trong (${s.bracket[0]}, ${s.bracket[1]}]`}
                  {s.confidence_interval &&
                    ` · khoảng tin cậy [${s.confidence_interval[0]}, ${s.confidence_interval[1]}]`}
                </p>
                {s.status && <StatusBadge kind="search" status={s.status} />}
              </li>
            ))}
          </ul>
        )}
        <ul className="space-y-1 text-sm" data-testid="tieu-chi-report">
          {results.criteria.map((r) => (
            <li key={r.index}>
              <strong>
                {r.status === 'pass' ? 'Đạt' : r.status === 'fail' ? 'Không đạt' : 'Chưa kết luận'}
              </strong>
              {criteria[r.index] ? ` · ${criterionText(criteria[r.index])}` : ''}
              <span className="block text-muted-foreground">{r.detail}</span>
            </li>
          ))}
        </ul>
      </Section>

      <Section n={5} title="Toàn bộ run">
        <Table
          caption="Run"
          head={[
            'Attack',
            'Level',
            'Phạm vi',
            'Trạng thái',
            'Mức sụt',
            'Thời gian',
            'Lý do, giải trình',
          ]}
        >
          {snapshot.runs.map((run) => (
            <tr key={run.run_id}>
              <td className={td}>{run.attack_spec_name}</td>
              <td className={td}>{run.level}</td>
              <td className={td}>{SCOPE_LABEL[run.scope]}</td>
              <td className={td}>
                <StatusBadge kind="run" status={run.status} />
              </td>
              <td className={td}>{percent(run.metrics?.relative_drop)}</td>
              <td className={td}>{formatDuration(run.processing_seconds)}</td>
              <td className={td}>
                {[run.status_reason, run.explanation].filter(Boolean).join(' · ') || '—'}
              </td>
            </tr>
          ))}
        </Table>
      </Section>

      <Section n={6} title="Failure case đã review">
        {snapshot.reviewed_cases.length === 0 ? (
          <p className="text-sm text-muted-foreground">Không có.</p>
        ) : (
          <ul className="grid gap-2 md:grid-cols-2">
            {snapshot.reviewed_cases.map((c) => (
              <li key={c.failure_case_id} className="rounded-lg border p-3 text-sm">
                <Link
                  to={`/failure-cases/${c.failure_case_id}?run=${c.run_id}`}
                  className="font-medium hover:underline"
                >
                  Ảnh {c.image_id}
                </Link>{' '}
                · {c.attack_spec_name} level {c.level}
                {c.required ? ' · bắt buộc' : ''}
                <p>
                  {SEVERITY_LABEL[c.verdict.severity]}, {KIND_LABEL[c.verdict.kind]} (v
                  {c.verdict.version}, {c.verdict.reviewer.full_name})
                </p>
                {c.verdict.mitigation && (
                  <p className="text-muted-foreground">{c.verdict.mitigation}</p>
                )}
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section n={7} title="Lịch sử">
        {history.related_experiments.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Không có experiment nào khác cùng model và dataset.
          </p>
        ) : (
          <Table
            caption="Experiment liên quan"
            head={['Experiment', 'Protocol', 'Trạng thái', 'Người tạo', 'Tạo lúc']}
          >
            {history.related_experiments.map((x) => (
              <tr key={x.id}>
                <td className={td}>{x.name}</td>
                <td className={td}>
                  {x.protocol.name} v{x.protocol_version}
                  {x.dev ? ' (dev)' : ''}
                </td>
                <td className={td}>
                  <StatusBadge kind="experiment" status={x.status} />
                </td>
                <td className={td}>{x.owner.full_name}</td>
                <td className={td}>{formatDateTime(x.created_at)}</td>
              </tr>
            ))}
          </Table>
        )}
        <ol className="space-y-1 text-sm">
          {history.timeline.map((event, i) => (
            <li key={i}>
              {formatDateTime(event.at)} · {TIMELINE_LABEL[event.action]} · {event.actor.full_name}
            </li>
          ))}
        </ol>
        <p className="text-sm text-muted-foreground">{history.comments_count} bình luận.</p>
      </Section>

      <Section n={8} title="Tái lập">
        <Table
          caption="Tái lập"
          head={['Run', 'Fingerprint', 'Git commit', 'Docker image', 'Thư viện']}
        >
          {snapshot.reproducibility.map((r) => (
            <tr key={r.run_id}>
              <td className={td}>
                <Hash value={r.run_id} />
              </td>
              <td className={td}>
                <Hash value={r.fingerprint} />
              </td>
              <td className={td}>
                <Hash value={r.git_commit} />
                {r.git_dirty && <span className="block text-destructive">Code chưa commit</span>}
              </td>
              <td className={td}>
                <Hash value={r.docker_image_digest} />
              </td>
              <td className={td}>
                {r.lib_versions
                  ? Object.entries(r.lib_versions)
                      .map(([k, v]) => `${k} ${v}`)
                      .join(', ')
                  : '—'}
              </td>
            </tr>
          ))}
        </Table>
      </Section>

      <Section n={9} title="Tài nguyên">
        <p className="text-sm">
          Thời gian xử lý đã dùng {formatDuration(snapshot.resources.processing_seconds_used)}
          {snapshot.resources.limit.kind === 'time'
            ? ` / giới hạn ${formatDuration(Number(snapshot.resources.limit.value))}`
            : ` · ngân sách ${snapshot.resources.limit.value}`}
        </p>
      </Section>
    </div>
  )
}

/** Nút tải cho người có `report.export`: mỗi lần bấm xin URL mới (ghi `report.downloaded`). */
export function DownloadButtons({ report }: { report: ReportView }) {
  const download = useDownloadReport(report.id)
  const start = (format: ReportDownload['format']) =>
    download.mutate(format, {
      onSuccess: (d) => {
        const url = artifactSrc(d.url)
        if (url) window.location.assign(url)
      },
    })
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-2">
        <Button onClick={() => start('pdf')} disabled={download.isPending}>
          <FileDown aria-hidden />
          Tải PDF
        </Button>
        <Button variant="outline" onClick={() => start('json')} disabled={download.isPending}>
          <FileDown aria-hidden />
          Tải JSON
        </Button>
      </div>
      {download.isError && <FormAlert>{errorMessage(download.error)}</FormAlert>}
    </div>
  )
}

/** Report chính thức (requirements.md Phase 8, Frontend; plan task 32). */
export function ReportPage() {
  const { id = '' } = useParams()
  const { data: me } = useMe()
  const detail = useReport(id)
  const regenerate = useRegenerateReport(id)
  if (detail.isPending) return <PageLoading />
  if (detail.isError) {
    return (
      <div className="p-4 md:p-6">
        <LoadError onRetry={() => void detail.refetch()} retrying={detail.isFetching} />
      </div>
    )
  }
  const { report, snapshot } = detail.data
  const exporter = can(me, 'report.export')
  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6 p-4 md:p-6">
      <header className="flex flex-col gap-2">
        <Link to="/reports" className="text-sm text-muted-foreground hover:underline">
          ← Report
        </Link>
        <h1 className="text-2xl font-semibold break-all">{report.experiment_name}</h1>
        <p className="text-sm text-muted-foreground">
          {REPORT_STATUS_LABEL[report.status]} · duyệt bởi {report.approved_by.full_name},{' '}
          {formatDateTime(report.approved_at)} ·{' '}
          <Link to={`/experiments/${report.experiment_id}`} className="hover:underline">
            Xem experiment
          </Link>
        </p>
      </header>
      {report.status === 'ready' && (
        <div
          className="flex flex-col gap-1 rounded-xl border-2 border-emerald-600 p-4"
          data-testid="dai-chinh-thuc"
        >
          <p className="flex items-center gap-2 font-semibold">
            <ShieldCheck aria-hidden className="size-5 text-emerald-600" />
            {OFFICIAL}
          </p>
          <p className="text-sm">
            Mã report <span className="font-mono break-all">{report.id}</span>
          </p>
          <p className="text-sm">
            Xác minh file tại{' '}
            <Link to={`/verify/${report.id}`} className="underline">
              /verify/{report.id}
            </Link>
          </p>
          <dl className="text-sm">
            <dt className="text-muted-foreground">SHA-256 của PDF</dt>
            <dd>
              <Hash value={report.pdf_sha256} />
            </dd>
            <dt className="text-muted-foreground">SHA-256 của JSON</dt>
            <dd>
              <Hash value={report.json_sha256} />
            </dd>
          </dl>
        </div>
      )}
      {report.status === 'ready' && exporter && <DownloadButtons report={report} />}
      {report.status === 'generating' && (
        <p className="text-muted-foreground" role="status">
          Report đang được sinh; trang tự cập nhật khi xong.
        </p>
      )}
      {report.status === 'failed' && (
        <div className="flex flex-col gap-2">
          <FormAlert>
            Sinh report bị lỗi sau 3 lần thử. Experiment vẫn ở trạng thái đã chấp nhận.
          </FormAlert>
          {exporter && (
            <Button
              className="self-start"
              onClick={() => regenerate.mutate()}
              disabled={regenerate.isPending}
            >
              Sinh lại
            </Button>
          )}
          {regenerate.isError && <FormAlert>{errorMessage(regenerate.error)}</FormAlert>}
        </div>
      )}
      {snapshot && <SnapshotView snapshot={snapshot} />}
    </div>
  )
}
