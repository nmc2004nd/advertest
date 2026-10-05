import { useQuery } from '@tanstack/react-query'
import {
  Activity,
  ArrowRight,
  BadgeCheck,
  ChevronRight,
  CircleCheck,
  Eye,
  FileText,
  FlaskConical,
  ListChecks,
  Plus,
  Send,
} from 'lucide-react'
import { Link } from 'react-router'

import { apiGet } from '@/api/client'
import {
  PENDING_COUNT_LIMIT,
  PENDING_USERS_QUERY_KEY,
  pendingCountLabel,
} from '@/auth/pending-count'
import { can } from '@/auth/permissions'
import { ROLE_LABELS } from '@/auth/roles'
import { useMe } from '@/auth/useMe'
import { Avatar } from '@/components/Avatar'
import { StatusBadge } from '@/components/status/StatusBadge'
import { GradientWaves } from '@/components/background/GradientWaves'
import { Button } from '@/components/ui/button'
import type { ExperimentSummary } from '@/contracts/api'
import type { Role, UserAdminPage } from '@/contracts/schemas'
import { EngineerHome } from '@/features/experiments/EngineerHome'
import { humanTime } from '@/features/experiments/format'
import { FlowRail } from '@/features/flow/FlowRail'
import type { StageId, StageView } from '@/features/flow/flow'
import { useFlow } from '@/features/flow/useFlow'
import { ReviewerHome } from '@/features/reviews/ReviewerHome'
import { useCountUp } from '@/lib/useCountUp'
import { cn } from '@/lib/utils'
import { PageHeader, SectionTitle } from '@/layout/PageHeader'
import { FloatingDecor } from '@/components/background/FloatingDecor'
import { BANNER_DECOR } from '@/components/background/decor-presets'

/** Vì sao nên làm việc này bây giờ: một câu giải thích, nói như đồng nghiệp. */
const WHY: Record<StageId, string> = {
  accounts: 'Người mới chưa vào được hệ thống cho tới khi bạn duyệt và gán vai trò cho họ.',
  protocol:
    'Kỹ sư cần một protocol đã chốt để biết phải chạy những attack nào và ngưỡng đạt là bao nhiêu.',
  configure:
    'Chọn protocol, model, slice ảnh và attack trong 6 bước. Hệ thống ước lượng thời gian trước khi chạy.',
  run: 'Worker đang xử lý. Bạn có thể làm việc khác; hệ thống gửi email khi xong.',
  submit:
    'Xem nhanh failure case cho chắc, rồi gửi cho một reviewer độc lập. Sau khi gửi, experiment được khóa để giữ nguyên kết quả.',
  review:
    'Một kỹ sư đang chờ kết luận của bạn. Xem các case bắt buộc rồi chấp nhận, yêu cầu sửa hoặc từ chối.',
  report: 'Report chính thức có mã xác minh; người ngoài kiểm tra được file bằng trang xác minh.',
}

/** Tên gọi tiếng Việt: từ cuối của họ tên ("Nguyễn Thu Linh" → "Linh"). */
function givenName(fullName: string): string {
  const parts = fullName.trim().split(/\s+/)
  return parts[parts.length - 1] ?? fullName
}

/** Một câu tóm tắt tình hình hôm nay. */
function summarySentence(stages: readonly StageView[], experiments: ExperimentSummary[]): string {
  const waiting = stages.filter((s) => s.state === 'action' && s.cta).length
  const running = experiments.filter((e) => e.status === 'running' || e.status === 'queued').length
  const parts = [
    waiting > 0 ? `Có ${waiting} việc đang chờ bạn.` : 'Hiện không có việc nào chờ bạn.',
    running > 0
      ? `${running} experiment đang chạy trên máy của nhóm.`
      : 'Không có experiment nào đang chạy.',
  ]
  return parts.join(' ')
}

/**
 * Trang chủ kiểu bảng điều khiển (tham khảo beehiiv): lời chào, banner cảnh 3D chứa đúng một việc
 * nên làm tiếp, bốn thẻ số liệu, rồi hai cột: bên trái việc của tôi và việc gần đây của nhóm, bên
 * phải checklist quy trình (requirements.md Phase 4, mục Điều hướng).
 */
export function HomePage() {
  const { data: me } = useMe()
  const flow = useFlow()
  if (!me) return null
  return (
    <div className="enter mx-auto flex max-w-[1180px] flex-col gap-6 px-4 py-7 md:px-8 md:py-9">
      <PageHeader
        title={<>Chào {givenName(me.full_name)} 👋</>}
        description={
          me.roles.length > 0 && !flow.loading
            ? summarySentence(flow.stages, flow.experiments)
            : 'Đây là tình hình kiểm định của nhóm bạn hôm nay.'
        }
      />
      {me.roles.length === 0 ? (
        <p className="panel p-5 text-muted-foreground">
          Tài khoản của bạn chưa có vai trò nào. Hãy nhắn quản trị viên để được cấp quyền.
        </p>
      ) : (
        <>
          <NextActionCard next={flow.next} loading={flow.loading} />
          {can(me, 'experiment.read') && <TeamPulse experiments={flow.experiments} />}
          <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
            <div className="flex min-w-0 flex-col gap-6">
              <section aria-labelledby="viec-cua-toi" className="flex flex-col gap-3">
                <SectionTitle id="viec-cua-toi" title="Việc của tôi" />
                <div
                  className={cn('grid grid-cols-1 gap-4', me.roles.length > 1 && 'md:grid-cols-2')}
                >
                  {me.roles.map((role) => (
                    <RoleBlock key={role} role={role} />
                  ))}
                </div>
              </section>
              {can(me, 'experiment.read') && (
                <RecentExperiments
                  experiments={flow.experiments.filter((e) => e.owner.id !== me.id)}
                  canCreate={can(me, 'experiment.create')}
                />
              )}
            </div>
            <div className="flex flex-col gap-6 lg:sticky lg:top-6">
              <FlowRail stages={flow.stages} roles={me.roles} />
              <Resources />
            </div>
          </div>
        </>
      )}
    </div>
  )
}

/**
 * Banner cảnh lụa 3D chứa một việc duy nhất nên làm tiếp, kèm lý do và một nút; không có việc thì
 * nói rõ là không có. Lớp phủ tối bên trái giữ chữ trắng đạt tương phản trên mọi màu của cảnh.
 */
function NextActionCard({ next, loading }: { next: StageView | null; loading: boolean }) {
  if (loading) {
    return <div className="panel h-[184px] animate-pulse" aria-hidden />
  }
  const cta = next?.cta
  const done = !next || !cta
  return (
    <div
      role={done ? 'status' : undefined}
      className="relative isolate overflow-hidden rounded-2xl shadow-[0_12px_32px_-12px_rgba(76,29,149,0.45)]"
      data-testid="viec-tiep-theo"
    >
      <GradientWaves className="absolute inset-0 -z-10" scale={0.8} />
      <div
        aria-hidden
        className="absolute inset-0 -z-10 bg-gradient-to-r from-[#1e1b4b]/80 via-[#1e1b4b]/45 to-transparent"
      />
      <FloatingDecor items={BANNER_DECOR} className="hidden md:block" />
      <div className="relative z-10 flex min-h-[184px] flex-col justify-center gap-5 p-6 text-white sm:flex-row sm:items-center sm:justify-between md:px-8 md:pr-[30%]">
        {done ? (
          <div className="flex max-w-[60ch] items-start gap-4">
            <span className="grid size-11 shrink-0 place-items-center rounded-full bg-white/15 backdrop-blur">
              <CircleCheck className="size-5" aria-hidden />
            </span>
            <div className="flex flex-col gap-1">
              <p className="text-[20px] font-semibold tracking-[-0.02em]">
                Bạn đã xong hết việc của mình 🎉
              </p>
              <p className="text-[14.5px] leading-6 text-white/85">
                Checklist "Quy trình của nhóm" cho biết mọi người đang ở bước nào, nếu bạn muốn hỗ
                trợ ai đó.
              </p>
            </div>
          </div>
        ) : (
          <>
            <div className="flex max-w-[60ch] flex-col gap-1.5">
              <span className="inline-flex items-center gap-2 self-start rounded-full bg-white/15 px-3 py-1 text-[12.5px] font-semibold backdrop-blur">
                <span className="status-dot live size-1.5 text-[#fde68a]" aria-hidden />
                Việc nên làm tiếp
              </span>
              <p className="text-[22px] leading-7 font-semibold tracking-[-0.02em]">{next.title}</p>
              <p className="text-[14.5px] leading-6 text-white/85">{WHY[next.id]}</p>
            </div>
            <Button
              asChild
              size="lg"
              className="shrink-0 self-start bg-white text-[#1e293b] shadow-[0_6px_20px_rgba(15,23,42,0.25)] hover:bg-white/90 sm:self-auto"
            >
              <Link to={cta.to}>
                {cta.label}
                <ArrowRight aria-hidden />
              </Link>
            </Button>
          </>
        )}
      </div>
    </div>
  )
}

/** Tình hình của nhóm: bốn thẻ số liệu, mỗi thẻ dẫn tới danh sách đã lọc sẵn. */
function TeamPulse({ experiments }: { experiments: ExperimentSummary[] }) {
  const by = (...s: ExperimentSummary['status'][]) =>
    experiments.filter((e) => s.includes(e.status)).length
  const running = by('running', 'queued')
  const items = [
    {
      label: 'Đang chạy',
      value: running,
      icon: Activity,
      tile: '[--tile-bg:#e0f2fe] [--tile-fg:#0369a1]',
      live: running > 0,
      to: '/experiments?status=running',
    },
    {
      label: 'Xong, chưa gửi duyệt',
      value: by('completed'),
      icon: Send,
      tile: '[--tile-bg:#ffedd5] [--tile-fg:#c2410c]',
      to: '/experiments?status=completed',
    },
    {
      label: 'Đang được review',
      value: by('submitted_for_review', 'in_review'),
      icon: Eye,
      tile: '[--tile-bg:#f5f3ff] [--tile-fg:#6d28d9]',
      to: '/experiments?status=in_review',
    },
    {
      label: 'Đã chấp nhận',
      value: by('approved'),
      icon: BadgeCheck,
      tile: '[--tile-bg:#dcfce7] [--tile-fg:#15803d]',
      to: '/experiments?status=approved',
    },
  ]
  return (
    <section aria-label="Tình hình của nhóm">
      <dl className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {items.map((item) => (
          <div key={item.label}>
            <Link
              to={item.to}
              className="panel lift group flex h-full flex-col gap-3 p-4 focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
            >
              <span className="flex items-center justify-between gap-2">
                <span className={cn('tile size-9', item.tile)} aria-hidden>
                  <item.icon className="size-[18px]" />
                </span>
                {item.live ? (
                  <span className="delta [--approved:var(--detect-strong)]">
                    <span className="status-dot live size-1.5" aria-hidden />
                    Trực tiếp
                  </span>
                ) : (
                  <ChevronRight
                    className="size-4 text-muted-foreground transition-transform group-hover:translate-x-0.5"
                    aria-hidden
                  />
                )}
              </span>
              <dt className="text-[13px] text-muted-foreground">{item.label}</dt>
              <dd className="-mt-2 text-[28px] leading-none font-semibold tracking-[-0.03em] tabular-nums">
                <CountUp value={item.value} />
              </dd>
            </Link>
          </div>
        ))}
      </dl>
    </section>
  )
}

/** Thẻ tài nguyên: lối tắt tới những trang hay cần đọc lại. */
function Resources() {
  const links = [
    {
      to: '/protocols',
      label: 'Protocol đang dùng',
      hint: 'Attack và ngưỡng đạt đã chốt',
      icon: ListChecks,
    },
    { to: '/reports', label: 'Report đã phát hành', hint: 'Kèm mã xác minh', icon: FileText },
    {
      to: '/experiments',
      label: 'Tất cả experiment',
      hint: 'Lọc theo trạng thái, người chạy',
      icon: FlaskConical,
    },
  ]
  return (
    <section aria-labelledby="tai-nguyen" className="panel flex flex-col gap-2 p-5">
      <h2 id="tai-nguyen" className="text-[16px] font-semibold">
        Tài nguyên
      </h2>
      <ul className="-mx-2 flex flex-col">
        {links.map((l) => (
          <li key={l.to}>
            <Link
              to={l.to}
              className="group flex min-h-12 items-center gap-3 rounded-[10px] px-2 py-1.5 transition-colors hover:bg-muted focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
            >
              <span className="tile size-8" aria-hidden>
                <l.icon className="size-4" />
              </span>
              <span className="flex min-w-0 flex-1 flex-col">
                <span className="text-[14px] font-medium">{l.label}</span>
                <span className="text-[12.5px] text-muted-foreground">{l.hint}</span>
              </span>
              <ChevronRight className="size-4 text-muted-foreground" aria-hidden />
            </Link>
          </li>
        ))}
      </ul>
    </section>
  )
}

function CountUp({ value }: { value: number }) {
  return <>{useCountUp(value)}</>
}

/**
 * Gần đây trong nhóm: việc của những người khác (ai làm, đang ở đâu, xong khi nào). Việc của chính
 * mình nằm ở "Việc của tôi" nên không lặp lại ở đây.
 */
function RecentExperiments({
  experiments,
  canCreate,
}: {
  experiments: ExperimentSummary[]
  canCreate: boolean
}) {
  return (
    <section aria-labelledby="gan-day" className="flex flex-col gap-3">
      <SectionTitle
        id="gan-day"
        title="Gần đây trong nhóm"
        action={
          <Link
            to="/experiments"
            className="inline-flex min-h-9 items-center gap-0.5 rounded-md text-sm font-medium text-detect-strong hover:underline"
          >
            Xem tất cả
            <ChevronRight className="size-4" aria-hidden />
          </Link>
        }
      />
      {experiments.length === 0 ? (
        <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-pink/40 bg-pink-soft px-6 py-10 text-center">
          <span
            className="tile size-11 [--tile-bg:#fff] [--tile-fg:var(--pink)] shadow-sm"
            aria-hidden
          >
            <FlaskConical className="size-5" />
          </span>
          <p className="text-[15px] font-semibold">Chưa có ai khác chạy experiment</p>
          <p className="max-w-sm text-[13.5px] leading-5 text-muted-foreground">
            Khi đồng nghiệp chạy experiment, bạn sẽ thấy ở đây ai làm, đang ở bước nào và xong khi
            nào.
          </p>
          {canCreate && (
            <Link
              to="/experiments/new"
              className="mt-1 inline-flex min-h-11 items-center gap-2 rounded-[10px] border border-line bg-surface-solid px-4 text-[14px] font-semibold shadow-sm transition-colors hover:bg-muted focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
            >
              <Plus className="size-4" aria-hidden />
              Tạo experiment
            </Link>
          )}
        </div>
      ) : (
        <ul className="panel divide-y divide-line overflow-hidden">
          {experiments.slice(0, 5).map((e) => (
            <li key={e.id}>
              <Link
                to={`/experiments/${e.id}`}
                className="group flex items-center gap-3 px-5 py-3.5 transition-colors hover:bg-muted focus-visible:bg-muted focus-visible:outline-none"
              >
                <Avatar name={e.owner.full_name} size={32} />
                <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                  <span className="truncate text-[14.5px] font-semibold transition-colors group-hover:text-cta">
                    {e.name}
                  </span>
                  <span className="truncate text-[13px] text-muted-foreground">
                    {e.owner.full_name} chạy trên {e.slice.size} ảnh, {humanTime(e)}
                  </span>
                </span>
                <StatusBadge kind="experiment" status={e.status} />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function RoleBlock({ role }: { role: Role }) {
  return (
    <section className="panel flex flex-col gap-3 p-5">
      <h3 className="flex items-center gap-2 text-[13px] font-semibold text-muted-foreground">
        <span
          aria-hidden
          className="size-1.5 rounded-full bg-gradient-to-r from-[#2563eb] to-[#ec4899]"
        />
        {ROLE_LABELS[role]}
      </h3>
      {role === 'admin' ? (
        <PendingUsers />
      ) : role === 'engineer' ? (
        <EngineerHome />
      ) : role === 'reviewer' ? (
        <ReviewerHome />
      ) : (
        <p className="text-muted-foreground">Sắp có.</p>
      )}
    </section>
  )
}

function PendingUsers() {
  const { data, isPending, isError } = useQuery({
    queryKey: PENDING_USERS_QUERY_KEY,
    queryFn: () =>
      apiGet<UserAdminPage>(`/admin/users?status=pending&limit=${PENDING_COUNT_LIMIT}`),
  })
  if (isPending) return <p className="text-muted-foreground">Đang tải…</p>
  if (isError) return <p className="text-destructive">Không tải được số tài khoản chờ duyệt.</p>
  return (
    <div className="flex flex-col gap-3">
      <Link
        to="/admin/users"
        className="inline-flex min-h-11 items-baseline gap-2 rounded-md focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
      >
        <span
          className="text-4xl font-[760] tracking-[-0.05em] tabular-nums"
          data-testid="so-cho-duyet"
        >
          {pendingCountLabel(data)}
        </span>
        <span className="text-muted-foreground">tài khoản chờ duyệt</span>
      </Link>
    </div>
  )
}
