import type { ReactNode } from 'react'
import { Link } from 'react-router'

import { FloatingDecor } from '@/components/background/FloatingDecor'
import { GradientWaves } from '@/components/background/GradientWaves'
import { AUTH_DECOR } from '@/components/background/decor-presets'

import { AuthShowcase } from './AuthShowcase'
import { BrandMark } from './BrandMark'

/**
 * Khung trang công khai (đăng nhập, yêu cầu truy cập, đặt lại mật khẩu), tham khảo màn onboarding
 * của beehiiv: cả trang là các dải sóng lớn chuyển động (con trỏ làm sóng phồng, bấm tạo gợn), thẻ
 * trắng chứa form nổi bên trái, thẻ minh họa và các vật 3D kéo thả được bên phải (từ 1024px).
 */
export function PublicLayout({
  title,
  lead,
  children,
}: {
  title: string
  /** Một câu dưới tiêu đề, nói người dùng sắp làm gì. */
  lead?: ReactNode
  children: ReactNode
}) {
  return (
    <div className="relative isolate min-h-dvh overflow-hidden bg-[#c7c9f5]">
      <GradientWaves variant="flow" className="fixed inset-0 -z-10" />
      <FloatingDecor items={AUTH_DECOR} className="fixed z-20 hidden lg:block" />
      <div className="relative min-h-dvh lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(0,1.08fr)]">
        <div className="flex min-h-dvh items-center justify-center px-4 pt-[max(1rem,env(safe-area-inset-top))] pb-[max(1rem,env(safe-area-inset-bottom))] sm:px-8">
          <div className="enter relative z-30 flex w-full max-w-[460px] flex-col gap-7 rounded-[24px] bg-surface-solid p-7 shadow-[0_30px_80px_-24px_rgba(30,27,75,0.5)] sm:p-10">
            <Link
              to="/"
              className="inline-flex min-h-11 items-center gap-2.5 self-start rounded-md text-[17px] font-bold tracking-[-0.02em] focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
            >
              <BrandMark className="size-9" />
              AdverTest
            </Link>
            <main className="flex flex-col gap-7">
              <div className="flex flex-col gap-2">
                <h1 className="text-[28px] leading-tight font-bold tracking-[-0.03em]">{title}</h1>
                {lead && <p className="text-[15px] leading-6 text-muted-foreground">{lead}</p>}
              </div>
              <div className="flex flex-col gap-6">{children}</div>
            </main>
            <footer className="border-t border-line pt-4 text-[12.5px] text-muted-foreground">
              Kết luận chỉ chính thức sau khi một reviewer độc lập duyệt.
            </footer>
          </div>
        </div>
        <aside aria-label="Giới thiệu AdverTest" className="hidden lg:block">
          <div className="sticky top-0 h-dvh">
            <AuthShowcase />
          </div>
        </aside>
      </div>
    </div>
  )
}
