import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Ellipsis,
  LoaderCircle,
  LogOut,
  Moon,
  Plus,
  Search,
  Sun,
  TriangleAlert,
} from 'lucide-react'
import { useCallback, useState } from 'react'
import { Link, Outlet, useLocation, useNavigate } from 'react-router'

import { apiGet, apiSend } from '@/api/client'
import { ROLE_LABELS } from '@/auth/roles'
import type { HealthResponse } from '@/contracts/api'
import type { Role } from '@/contracts/schemas'

import { RequirePermission } from '@/auth/RequirePermission'
import { AUTHENTICATED } from '@/auth/permissions'
import { useMe } from '@/auth/useMe'
import { Avatar } from '@/components/Avatar'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { useFlow } from '@/features/flow/useFlow'
import { useTheme } from '@/lib/theme'
import { cn } from '@/lib/utils'
import { isNavActive, splitTabs, visibleNav, type NavItem } from '@/nav/config'

import { BrandMark } from './BrandMark'
import { useCommandShortcut } from './command-utils'
import { CommandPalette } from './CommandPalette'
import { GradientWaves } from '@/components/background/GradientWaves'

/**
 * Khung ứng dụng cho người đã đăng nhập (requirements.md Phase 4, mục Điều hướng):
 * desktop ≥ 1280px sidebar; tablet 768–1279px cột icon; điện thoại < 768px thanh tab dưới đáy.
 */
export function AppShell() {
  return (
    <RequirePermission requirement={AUTHENTICATED}>
      <ShellLayout />
    </RequirePermission>
  )
}

function ShellLayout() {
  const { data: me } = useMe()
  const items = visibleNav(me)
  const [searching, setSearching] = useState(false)
  const openSearch = useCallback(() => setSearching(true), [])
  useCommandShortcut(openSearch)
  const flow = useFlow()
  // Số việc đang chờ chính người dùng ở từng mục điều hướng (badge trong sidebar).
  const badges: Record<string, number> = {}
  for (const stage of flow.stages) {
    if (stage.state !== 'action' || !stage.cta) continue
    const path = stage.cta.to.split('?')[0].replace(/\/[0-9a-f-]{36}$/, '')
    badges[path] = (badges[path] ?? 0) + 1
  }
  return (
    <div className="relative isolate min-h-dvh bg-background md:flex">
      {/* Nền: các dải sóng lớn chuyển động, phủ lớp sáng để bảng và chữ vẫn dễ đọc. */}
      <GradientWaves variant="flow" className="fixed inset-0 z-0" />
      <div aria-hidden className="fixed inset-0 z-0 bg-background/72" />
      <a
        href="#noi-dung"
        className="sr-only z-50 rounded-md bg-primary px-3 py-2 text-primary-foreground focus:not-sr-only focus:fixed focus:top-2 focus:left-2"
      >
        Bỏ qua điều hướng
      </a>
      <SideNav
        items={items}
        name={me?.full_name}
        roles={me?.roles}
        onSearch={openSearch}
        badges={badges}
        running={
          flow.experiments.filter((e) => e.status === 'running' || e.status === 'queued').length
        }
        footer={
          <div className="flex items-center gap-1 max-xl:flex-col">
            <ThemeButton />
            <LogoutButton />
          </div>
        }
      />
      <CommandPalette open={searching} onOpenChange={setSearching} />
      <div className="relative z-10 flex min-w-0 flex-1 flex-col">
        <SystemNotice
          running={
            flow.experiments.filter((e) => e.status === 'running' || e.status === 'queued').length
          }
        />
        <main
          id="noi-dung"
          className="min-w-0 flex-1 pr-[env(safe-area-inset-right)] pb-[calc(4.5rem+env(safe-area-inset-bottom))] md:pb-0"
        >
          <Outlet />
        </main>
      </div>
      <BottomTabs items={items} />
    </div>
  )
}

const ICON_BUTTON =
  'inline-flex size-11 shrink-0 items-center justify-center rounded-[10px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none disabled:opacity-50'

/** Đổi giao diện sáng/tối (mặc định sáng). */
function ThemeButton() {
  const { theme, toggle } = useTheme()
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={theme === 'dark' ? 'Dùng giao diện sáng' : 'Dùng giao diện tối'}
      title={theme === 'dark' ? 'Giao diện sáng' : 'Giao diện tối'}
      className={ICON_BUTTON}
    >
      {theme === 'dark' ? (
        <Sun className="size-[18px]" aria-hidden />
      ) : (
        <Moon className="size-[18px]" aria-hidden />
      )}
    </button>
  )
}

/**
 * Thông báo hệ thống: chỉ hiện khi có điều đáng nói (đang có experiment chạy, hoặc hệ thống gặp
 * sự cố), viết thành câu để người dùng biết nên làm gì.
 */
function SystemNotice({ running }: { running: number }) {
  const health = useQuery({
    queryKey: ['health'],
    queryFn: () => apiGet<HealthResponse>('/health'),
    refetchInterval: 30_000,
  })
  const down = health.isError || health.data?.status === 'degraded'
  if (down) {
    const parts = [
      health.data && !health.data.postgres.ok && 'cơ sở dữ liệu',
      health.data && !health.data.minio.ok && 'kho ảnh',
    ].filter(Boolean)
    return (
      <div
        role="alert"
        className="flex min-h-11 items-center gap-2 border-b border-fail/25 bg-fail/8 px-4 text-sm text-fail md:px-8"
      >
        <TriangleAlert className="size-4 shrink-0" aria-hidden />
        <span>
          Hệ thống đang gặp sự cố{parts.length ? ` ở ${parts.join(' và ')}` : ''}. Dữ liệu của bạn
          vẫn an toàn; hãy thử lại sau ít phút hoặc báo quản trị viên.
        </span>
      </div>
    )
  }
  if (running === 0) return null
  return (
    <div
      role="status"
      className="flex min-h-11 items-center gap-2 border-b border-line bg-surface-raised px-4 text-sm md:px-8"
    >
      <LoaderCircle
        className="size-4 shrink-0 animate-spin text-detect-strong motion-reduce:animate-none"
        aria-hidden
      />
      <span className="min-w-0 flex-1 truncate">
        {running} experiment đang chạy. Bạn cứ làm việc khác, hệ thống sẽ gửi email khi xong.
      </span>
      <Link
        to="/experiments?status=running"
        className="shrink-0 font-medium text-detect-strong hover:underline"
      >
        Xem tiến độ
      </Link>
    </div>
  )
}

function navClass({ isActive }: { isActive: boolean }): string {
  return cn(
    'relative flex min-h-11 items-center gap-3 rounded-[10px] px-3 text-[14px] font-medium transition-[color,background-color] duration-150 focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none max-xl:justify-center',
    isActive && 'bg-pink-soft font-semibold text-foreground [&>svg]:text-pink',
    !isActive && 'text-muted-foreground hover:bg-muted hover:text-foreground',
  )
}

/**
 * Link của một mục điều hướng; tự tính trạng thái sáng (kể cả `exclude`: /experiments/new thuộc
 * mục "Tạo experiment", không làm mục "Experiment" sáng).
 */
function ItemLink({
  item,
  className,
  children,
  ...rest
}: {
  item: NavItem
  className: (state: { isActive: boolean }) => string
  children: React.ReactNode
  title?: string
  'aria-label'?: string
  onClick?: () => void
}) {
  const { pathname } = useLocation()
  const isActive = isNavActive(item, pathname)
  return (
    <Link
      to={item.path}
      className={className({ isActive })}
      aria-current={isActive ? 'page' : undefined}
      {...rest}
    >
      {children}
    </Link>
  )
}

/** Đầu sidebar kiểu "workspace" (beehiiv): logo, tên sản phẩm, tên nhóm. Không phải link. */
function Brand() {
  return (
    <div className="flex min-h-16 items-center gap-2.5 px-2 max-xl:justify-center">
      <BrandMark className="size-9" />
      <span className="hidden min-w-0 leading-tight xl:block">
        <span className="block truncate text-[15px] font-semibold tracking-[-0.02em]">
          AdverTest
        </span>
        <span className="block truncate text-[12.5px] text-muted-foreground">
          Nhóm kiểm định perception
        </span>
      </span>
    </div>
  )
}

/**
 * Thẻ tình trạng máy chạy test ở cuối sidebar (giống thẻ gói dịch vụ của beehiiv): hệ thống có
 * ổn không, bao nhiêu experiment đang chạy, bấm vào xem tiến độ.
 */
function ComputeCard({ running }: { running: number }) {
  const health = useQuery({
    queryKey: ['health'],
    queryFn: () => apiGet<HealthResponse>('/health'),
    refetchInterval: 30_000,
  })
  const ok = health.data?.status === 'ok'
  return (
    <Link
      to={running > 0 ? '/experiments?status=running' : '/experiments'}
      className="group relative hidden overflow-hidden rounded-xl border border-line bg-surface-solid p-3 transition-shadow hover:shadow-[0_8px_24px_rgba(16,24,40,0.08)] focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none xl:block"
    >
      <span
        aria-hidden
        className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-[#2563eb] via-[#7c3aed] to-[#ec4899]"
      />
      <span className="flex items-center gap-2 text-[13px] font-semibold">
        <span
          aria-hidden
          className={cn('status-dot size-2', ok ? 'live text-approved' : 'text-threshold')}
        />
        {health.isPending ? 'Đang kiểm tra hệ thống…' : ok ? 'Hệ thống sẵn sàng' : 'Hệ thống chậm'}
      </span>
      <span className="mt-1 block text-[12.5px] leading-5 text-muted-foreground">
        {running > 0
          ? `${running} experiment đang chạy trên worker của nhóm.`
          : 'Worker đang rảnh, có thể nhận experiment mới.'}
      </span>
      <span className="mt-2 flex h-1.5 overflow-hidden rounded-full bg-muted" aria-hidden>
        <span
          className={cn(
            'rounded-full bg-gradient-to-r from-[#2563eb] to-[#7c3aed]',
            running > 0 && 'shimmer',
          )}
          style={{ width: running > 0 ? `${Math.min(100, 30 + running * 20)}%` : '8%' }}
        />
      </span>
    </Link>
  )
}

function useLogout() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => apiSend<undefined>('POST', '/auth/logout'),
    onSettled: () => {
      queryClient.clear()
      void navigate('/login', { replace: true })
    },
  })
}

function LogoutButton() {
  const logout = useLogout()
  return (
    <button
      type="button"
      onClick={() => logout.mutate()}
      disabled={logout.isPending}
      title="Đăng xuất"
      aria-label="Đăng xuất"
      className={ICON_BUTTON}
    >
      <LogOut className="size-[18px]" aria-hidden />
    </button>
  )
}

function NavList({ items, badges }: { items: NavItem[]; badges?: Record<string, number> }) {
  return (
    <>
      {items.map((item) => {
        const badge = badges?.[item.path]
        return (
          <ItemLink
            key={item.path}
            item={item}
            className={navClass}
            title={item.label}
            aria-label={badge ? `${item.label} (${badge} việc chờ bạn)` : item.label}
          >
            <item.icon className="size-[18px] shrink-0" aria-hidden />
            <span className="hidden flex-1 xl:inline">{item.label}</span>
            {badge ? (
              <em
                aria-hidden
                className="absolute top-2 right-2 size-2 rounded-full bg-primary not-italic xl:static xl:size-auto xl:min-w-6 xl:rounded-full xl:bg-primary xl:px-1.5 xl:text-center xl:text-xs xl:font-semibold xl:text-primary-foreground"
              >
                <span className="hidden xl:inline">{badge}</span>
              </em>
            ) : null}
          </ItemLink>
        )
      })}
    </>
  )
}

/** Sidebar (desktop) và cột icon (tablet): cùng một phần tử, nhãn chỉ hiện từ 1280px. */
export function SideNav({
  items,
  name,
  roles,
  onSearch,
  badges,
  running,
  footer,
}: {
  items: NavItem[]
  name?: string
  roles?: readonly Role[]
  onSearch?: () => void
  badges?: Record<string, number>
  /** Số experiment đang chạy (thẻ tình trạng máy chạy test); bỏ trống thì không hiện thẻ. */
  running?: number
  /** Phần cuối sidebar (nút đăng xuất); khung ứng dụng truyền vào. */
  footer?: React.ReactNode
}) {
  // "Tạo experiment" là nút CTA ở thanh trên cùng, không lặp lại trong danh sách.
  const create = items.find((item) => item.path === '/experiments/new')
  const work = items.filter((item) => item !== create && !item.group && item.path !== '/account')
  const admin = items.filter((item) => item.group === 'admin')
  const account = items.find((item) => item.path === '/account')
  return (
    <aside
      aria-label="Điều hướng chính"
      className="sticky top-0 z-20 hidden h-dvh w-[76px] shrink-0 flex-col gap-3 border-r border-line bg-surface-solid pl-[env(safe-area-inset-left)] md:flex xl:w-60"
    >
      <div className="px-2 pt-2">
        <Brand />
      </div>
      <div className="flex flex-col gap-2 px-3">
        {create && (
          <Link
            to={create.path}
            aria-label={create.label}
            title={create.label}
            className="inline-flex min-h-11 items-center justify-center gap-2 rounded-[10px] bg-primary px-4 text-[14px] font-semibold text-primary-foreground shadow-sm transition-colors hover:bg-navy-hover focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
          >
            <Plus className="size-4 shrink-0" aria-hidden />
            <span className="hidden xl:inline">{create.label}</span>
          </Link>
        )}
        {onSearch && (
          <button
            type="button"
            onClick={onSearch}
            title="Tìm nhanh (Ctrl K)"
            aria-label="Tìm nhanh"
            className="inline-flex min-h-11 items-center gap-2 rounded-[10px] border border-line bg-surface-solid px-3 text-[14px] text-muted-foreground transition-colors hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none max-xl:justify-center max-xl:px-0"
          >
            <Search className="size-4 shrink-0" aria-hidden />
            <span className="hidden flex-1 text-left xl:inline">Tìm nhanh</span>
            <kbd className="hidden rounded-md bg-surface-raised px-1.5 font-sans text-[11px] xl:inline">
              Ctrl K
            </kbd>
          </button>
        )}
      </div>
      <nav className="flex flex-col gap-0.5 overflow-y-auto px-3 pt-1">
        <NavList items={work} badges={badges} />
        {admin.length > 0 && (
          <>
            <p className="mt-5 mb-1 hidden px-3 text-[12px] font-semibold tracking-wide text-muted-foreground uppercase xl:block">
              Quản trị
            </p>
            <div aria-hidden className="mx-3 my-2 border-t border-line xl:hidden" />
            <NavList items={admin} badges={badges} />
          </>
        )}
      </nav>
      <div className="mt-auto flex flex-col gap-3 p-3">
        {running !== undefined && <ComputeCard running={running} />}
        <div className="relative flex flex-col gap-1 border-t border-line pt-3">
          {account && (
            <ItemLink
              item={account}
              className={(state) => cn(navClass(state), 'min-h-14 gap-2.5 px-2')}
              title={account.label}
              aria-label={account.label}
            >
              <Avatar name={name} size={34} />
              <span className="hidden min-w-0 flex-col xl:flex">
                <span className="truncate text-[14px] font-semibold text-foreground">{name}</span>
                {roles && roles.length > 0 && (
                  <span className="truncate text-[12.5px] font-normal text-muted-foreground">
                    {roles.map((r) => ROLE_LABELS[r].split(' (')[0]).join(', ')}
                  </span>
                )}
              </span>
            </ItemLink>
          )}
          {!account && name && (
            <p className="hidden truncate px-3 text-sm text-muted-foreground xl:block">{name}</p>
          )}
          {footer}
        </div>
      </div>
    </aside>
  )
}

function tabClass({ isActive }: { isActive: boolean }): string {
  return cn(
    'flex min-h-14 flex-1 flex-col items-center justify-center gap-0.5 text-xs font-medium focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none',
    isActive ? 'text-detect-strong' : 'text-muted-foreground',
  )
}

/**
 * Danh sách mục trong bottom sheet "Thêm". Link tự đóng sheet qua `onNavigate`: không bọc trong
 * `DialogClose asChild` vì Slot của Radix gộp `className` dạng hàm thành chuỗi (sập trang).
 */
export function MoreLinks({ items, onNavigate }: { items: NavItem[]; onNavigate: () => void }) {
  return (
    <nav className="flex flex-col gap-1">
      {items.map((item) => (
        <ItemLink key={item.path} item={item} className={navClass} onClick={onNavigate}>
          <item.icon className="size-5 shrink-0" aria-hidden />
          <span>{item.label}</span>
        </ItemLink>
      ))}
    </nav>
  )
}

/** Thanh tab điện thoại: tối đa 4 ô, dư thì ô cuối là "Thêm" mở bottom sheet. */
export function BottomTabs({ items }: { items: NavItem[] }) {
  const { tabs, more } = splitTabs(items)
  const [moreOpen, setMoreOpen] = useState(false)
  if (items.length === 0) return null
  return (
    <nav
      aria-label="Điều hướng chính"
      className="fixed inset-x-0 bottom-0 z-40 flex border-t border-line bg-surface/95 backdrop-blur pr-[env(safe-area-inset-right)] pb-[env(safe-area-inset-bottom)] pl-[env(safe-area-inset-left)] md:hidden"
    >
      {tabs.map((item) => (
        <ItemLink key={item.path} item={item} className={tabClass}>
          <item.icon className="size-5" aria-hidden />
          <span className="max-w-full truncate px-1">{item.label}</span>
        </ItemLink>
      ))}
      {more.length > 0 && (
        <Dialog open={moreOpen} onOpenChange={setMoreOpen}>
          <DialogTrigger className={tabClass({ isActive: false })}>
            <Ellipsis className="size-5" aria-hidden />
            <span>Thêm</span>
          </DialogTrigger>
          <DialogContent>
            <DialogTitle>Thêm</DialogTitle>
            <DialogDescription className="sr-only">Các mục điều hướng khác</DialogDescription>
            <MoreLinks items={more} onNavigate={() => setMoreOpen(false)} />
          </DialogContent>
        </Dialog>
      )}
    </nav>
  )
}
