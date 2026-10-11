import { ChevronRight, CircleCheck, Plus } from 'lucide-react'
import { Link } from 'react-router'

import { Button } from '@/components/ui/button'

import type { TodoItem } from './todos'

/**
 * Danh sách việc cần làm ở đầu /home (requirements.md Phase R3, mục Trang chủ): mỗi việc có số lượng
 * và link tới đúng nơi xử lý; không có việc thì nói rõ và gợi ý một hành động.
 */
export function TodoList({
  todos,
  loading,
  failed,
  canCreate,
}: {
  todos: TodoItem[]
  loading: boolean
  failed: boolean
  /** Engineer: gợi ý "Tạo experiment Khám phá" khi không có việc. */
  canCreate: boolean
}) {
  return (
    <section aria-labelledby="viec-can-lam" className="panel flex flex-col gap-3 p-5">
      <h2 id="viec-can-lam" className="text-[17px] leading-6 font-semibold tracking-[-0.01em]">
        Việc cần làm
      </h2>
      {loading ? (
        <p className="text-sm text-muted-foreground" role="status">
          Đang tải việc cần làm…
        </p>
      ) : todos.length === 0 ? (
        failed ? null : (
          <div className="flex flex-col items-start gap-3" role="status">
            <p className="flex items-center gap-2 text-[15px]">
              <CircleCheck aria-hidden="true" className="size-5 shrink-0 text-muted-foreground" />
              Không có việc cần làm
            </p>
            {canCreate && (
              <Button asChild>
                <Link to="/experiments/new">
                  <Plus aria-hidden="true" />
                  Tạo experiment Khám phá
                </Link>
              </Button>
            )}
          </div>
        )
      ) : (
        <ul data-testid="todo-list" className="flex flex-col divide-y divide-line">
          {todos.map((todo) => (
            <li
              key={todo.kind}
              data-testid="todo-item"
              data-kind={todo.kind}
              className="flex flex-col gap-1 py-2 first:pt-0 last:pb-0"
            >
              <Link
                to={todo.to}
                className="flex min-h-11 items-center gap-3 rounded-lg px-2 hover:bg-surface-raised focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
              >
                <span className="min-w-9 rounded-full bg-detect/12 px-2 py-0.5 text-center text-sm font-semibold text-detect tabular-nums">
                  {todo.countLabel}
                </span>
                <span className="min-w-0 flex-1 font-medium">{todo.title}</span>
                <ChevronRight
                  aria-hidden="true"
                  className="size-4 shrink-0 text-muted-foreground"
                />
              </Link>
              {todo.count > 1 && todo.links.length > 0 && (
                <ul className="flex flex-col pl-14 text-sm">
                  {todo.links.map((link) => (
                    <li key={`${link.to}-${link.label}`}>
                      <Link
                        to={link.to}
                        className="inline-flex min-h-9 items-center break-all text-muted-foreground hover:text-foreground hover:underline"
                      >
                        {link.label}
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ul>
      )}
      {failed && (
        <p className="text-sm text-destructive">
          Không tải được một phần việc cần làm. Tải lại trang để thử lại.
        </p>
      )}
    </section>
  )
}
