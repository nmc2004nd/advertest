import { Link } from 'react-router'

import { ROLE_DESCRIPTIONS, ROLE_LABELS } from '@/auth/roles'
import { Button } from '@/components/ui/button'
import { roleValues } from '@/contracts/schemas'

/** Trang giới thiệu tối giản (requirements.md Phase 4; bản hoàn chỉnh ở Phase 11). */
export function LandingPage() {
  return (
    <div className="min-h-dvh px-4 pt-[max(1rem,env(safe-area-inset-top))] pb-[max(1rem,env(safe-area-inset-bottom))]">
      <main className="mx-auto flex max-w-2xl flex-col gap-8 py-10">
        <section className="flex flex-col gap-3">
          <h1 className="text-3xl font-semibold">AdverTest</h1>
          <p className="text-lg text-muted-foreground">
            Kiểm thử độ bền vững của model perception cho robot và xe tự hành: tấn công adversarial
            white-box và biến đổi mô phỏng điều kiện thực tế, đo mức suy giảm, và chỉ thành kết luận
            chính thức sau khi một kỹ sư độc lập duyệt.
          </p>
          <div className="flex flex-col gap-2 sm:flex-row">
            <Button asChild>
              <Link to="/request-access">Yêu cầu truy cập</Link>
            </Button>
            <Button asChild variant="outline">
              <Link to="/login">Đăng nhập</Link>
            </Button>
          </div>
        </section>
        <section className="flex flex-col gap-3">
          <h2 className="text-xl font-semibold">Ba vai trò</h2>
          <ul className="grid gap-3 md:grid-cols-3">
            {roleValues.map((role) => (
              <li key={role} className="rounded-xl border border-border p-4">
                <h3 className="font-medium">{ROLE_LABELS[role]}</h3>
                <p className="mt-1 text-sm text-muted-foreground">{ROLE_DESCRIPTIONS[role]}</p>
              </li>
            ))}
          </ul>
          <p className="text-sm text-muted-foreground">
            Tài khoản mới cần quản trị viên duyệt trước khi dùng được.
          </p>
        </section>
      </main>
    </div>
  )
}
