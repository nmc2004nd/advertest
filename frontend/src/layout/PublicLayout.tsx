import type { ReactNode } from 'react'
import { Link } from 'react-router'

/** Khung cho trang công khai (đăng nhập, yêu cầu truy cập...): một cột, rộng tối đa 28rem. */
export function PublicLayout({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="min-h-dvh px-4 pt-[max(1rem,env(safe-area-inset-top))] pb-[max(1rem,env(safe-area-inset-bottom))]">
      <header className="mx-auto flex max-w-md items-center py-2">
        <Link to="/" className="inline-flex min-h-11 items-center font-semibold">
          AdverTest
        </Link>
      </header>
      <main className="mx-auto flex max-w-md flex-col gap-6 py-6">
        <h1 className="text-2xl font-semibold">{title}</h1>
        {children}
      </main>
    </div>
  )
}
