import {
  CircleUser,
  ClipboardCheck,
  FlaskConical,
  House,
  Library,
  ScrollText,
  SquarePlus,
  Users,
  type LucideIcon,
} from 'lucide-react'

import { AUTHENTICATED, can, type Requirement } from '@/auth/permissions'
import type { Me } from '@/contracts/schemas'

/** Một mục điều hướng (requirements.md Phase 4, mục Điều hướng). */
export interface NavItem {
  path: string
  label: string
  icon: LucideIcon
  requirement: Requirement
  /** Trang đã có chưa: mục chỉ hiện khi người dùng có quyền **và** trang đã có. */
  implemented: boolean
  /** Đường dẫn con không làm mục này sáng (thuộc về mục khác, ví dụ /experiments/new). */
  exclude?: readonly string[]
}

/** Nguồn duy nhất của điều hướng; thứ tự ở đây là thứ tự hiển thị. */
export const NAV_ITEMS: readonly NavItem[] = [
  {
    path: '/home',
    label: 'Trang chủ',
    icon: House,
    requirement: AUTHENTICATED,
    implemented: true,
  },
  {
    path: '/experiments',
    label: 'Experiment',
    icon: FlaskConical,
    requirement: 'experiment.read',
    implemented: true,
    exclude: ['/experiments/new'],
  },
  {
    path: '/experiments/new',
    label: 'Tạo experiment',
    icon: SquarePlus,
    requirement: 'experiment.create',
    implemented: true,
  },
  {
    path: '/reviews',
    label: 'Duyệt',
    icon: ClipboardCheck,
    requirement: 'review.decide',
    implemented: false, // Phase 8
  },
  {
    path: '/admin/users',
    label: 'Người dùng',
    icon: Users,
    requirement: 'user.manage',
    implemented: true,
  },
  {
    path: '/admin/audit',
    label: 'Audit log',
    icon: ScrollText,
    requirement: 'audit.read',
    implemented: true,
  },
  {
    path: '/admin/attacks',
    label: 'Attack catalog',
    icon: Library,
    requirement: 'attack_catalog.manage',
    implemented: true,
  },
  {
    path: '/account',
    label: 'Tài khoản',
    icon: CircleUser,
    requirement: AUTHENTICATED,
    implemented: true,
  },
]

/** Mục có đang sáng ở `pathname` không: đúng đường dẫn hoặc trang con, trừ `exclude`. */
export function isNavActive(item: Pick<NavItem, 'path' | 'exclude'>, pathname: string): boolean {
  const under = (base: string) => pathname === base || pathname.startsWith(`${base}/`)
  return under(item.path) && !(item.exclude ?? []).some(under)
}

export function visibleNav(
  me: Pick<Me, 'roles'> | null | undefined,
  items: readonly NavItem[] = NAV_ITEMS,
): NavItem[] {
  return items.filter((item) => item.implemented && can(me, item.requirement))
}

/** Thanh tab điện thoại tối đa 4 ô: dư thì 3 mục đầu + "Thêm" chứa phần còn lại. */
export const MAX_TABS = 4

export function splitTabs(items: readonly NavItem[]): { tabs: NavItem[]; more: NavItem[] } {
  if (items.length <= MAX_TABS) return { tabs: [...items], more: [] }
  return { tabs: items.slice(0, MAX_TABS - 1), more: items.slice(MAX_TABS - 1) }
}
