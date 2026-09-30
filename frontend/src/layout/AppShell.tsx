import { Ellipsis } from 'lucide-react'
import { Link, Outlet, useLocation } from 'react-router'

import { RequirePermission } from '@/auth/RequirePermission'
import { AUTHENTICATED } from '@/auth/permissions'
import { useMe } from '@/auth/useMe'
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { cn } from '@/lib/utils'
import { isNavActive, splitTabs, visibleNav, type NavItem } from '@/nav/config'

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
  return (
    <div className="min-h-dvh md:flex">
      <SideNav items={items} name={me?.full_name} />
      <main
        id="noi-dung"
        className="min-w-0 flex-1 pr-[env(safe-area-inset-right)] pb-[calc(4.5rem+env(safe-area-inset-bottom))] md:pb-0"
      >
        <Outlet />
      </main>
      <BottomTabs items={items} />
    </div>
  )
}

function navClass({ isActive }: { isActive: boolean }): string {
  return cn(
    'flex min-h-11 items-center gap-3 rounded-lg px-3 text-sm font-medium transition-colors hover:bg-muted focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none',
    isActive && 'bg-muted text-foreground',
    !isActive && 'text-muted-foreground',
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

/** Sidebar (desktop) và cột icon (tablet): cùng một phần tử, nhãn chỉ hiện từ 1280px. */
export function SideNav({ items, name }: { items: NavItem[]; name?: string }) {
  return (
    <aside
      aria-label="Điều hướng chính"
      className="sticky top-0 hidden h-dvh w-16 shrink-0 flex-col gap-2 border-r border-border pl-[env(safe-area-inset-left)] md:flex xl:w-60"
    >
      <div className="flex min-h-14 items-center px-3 font-semibold">
        <span className="xl:hidden" aria-hidden>
          AT
        </span>
        <span className="hidden xl:inline">AdverTest</span>
      </div>
      <nav className="flex flex-col gap-1 px-2">
        {items.map((item) => (
          <ItemLink
            key={item.path}
            item={item}
            className={navClass}
            title={item.label}
            aria-label={item.label}
          >
            <item.icon className="size-5 shrink-0" aria-hidden />
            <span className="hidden xl:inline">{item.label}</span>
          </ItemLink>
        ))}
      </nav>
      {name && (
        <p className="mt-auto hidden truncate px-4 pb-4 text-sm text-muted-foreground xl:block">
          {name}
        </p>
      )}
    </aside>
  )
}

function tabClass({ isActive }: { isActive: boolean }): string {
  return cn(
    'flex min-h-14 flex-1 flex-col items-center justify-center gap-0.5 text-xs font-medium focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none',
    isActive ? 'text-foreground' : 'text-muted-foreground',
  )
}

/** Thanh tab điện thoại: tối đa 4 ô, dư thì ô cuối là "Thêm" mở bottom sheet. */
export function BottomTabs({ items }: { items: NavItem[] }) {
  const { tabs, more } = splitTabs(items)
  if (items.length === 0) return null
  return (
    <nav
      aria-label="Điều hướng chính"
      className="fixed inset-x-0 bottom-0 z-40 flex border-t border-border bg-background pr-[env(safe-area-inset-right)] pb-[env(safe-area-inset-bottom)] pl-[env(safe-area-inset-left)] md:hidden"
    >
      {tabs.map((item) => (
        <ItemLink key={item.path} item={item} className={tabClass}>
          <item.icon className="size-5" aria-hidden />
          <span className="max-w-full truncate px-1">{item.label}</span>
        </ItemLink>
      ))}
      {more.length > 0 && (
        <Dialog>
          <DialogTrigger className={tabClass({ isActive: false })}>
            <Ellipsis className="size-5" aria-hidden />
            <span>Thêm</span>
          </DialogTrigger>
          <DialogContent>
            <DialogTitle>Thêm</DialogTitle>
            <DialogDescription className="sr-only">Các mục điều hướng khác</DialogDescription>
            <nav className="flex flex-col gap-1">
              {more.map((item) => (
                <DialogClose key={item.path} asChild>
                  <ItemLink item={item} className={navClass}>
                    <item.icon className="size-5 shrink-0" aria-hidden />
                    <span>{item.label}</span>
                  </ItemLink>
                </DialogClose>
              ))}
            </nav>
          </DialogContent>
        </Dialog>
      )}
    </nav>
  )
}
