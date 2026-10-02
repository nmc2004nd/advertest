import { Link } from 'react-router'

import { useReviewQueue } from './api'

/** Khối reviewer trên trang chủ (plan task 31): số experiment chờ nhận, danh sách tôi đang review. */
export function ReviewerHome() {
  const waiting = useReviewQueue('waiting')
  const mine = useReviewQueue('mine')
  if (waiting.isPending || mine.isPending) {
    return <p className="text-muted-foreground">Đang tải…</p>
  }
  if (waiting.isError || mine.isError) {
    return <p className="text-destructive">Không tải được hàng đợi review.</p>
  }
  return (
    <div className="flex flex-col gap-3">
      <Link
        to="/reviews?status=waiting"
        className="inline-flex min-h-11 items-baseline gap-2 rounded-lg focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
      >
        <span className="text-3xl font-semibold" data-testid="so-cho-nhan">
          {waiting.data.length}
        </span>
        <span className="text-muted-foreground">experiment chờ nhận review</span>
      </Link>
      <div>
        <p className="text-sm font-medium">Tôi đang review</p>
        {mine.data.length === 0 ? (
          <p className="text-sm text-muted-foreground">Không có.</p>
        ) : (
          <ul className="flex flex-col">
            {mine.data.map((item) => (
              <li key={item.experiment.id}>
                <Link
                  to={`/reviews/${item.experiment.id}`}
                  className="flex min-h-11 flex-col justify-center rounded-lg px-2 py-1 text-sm hover:bg-muted"
                >
                  <span className="break-all">{item.experiment.name}</span>
                  <span className="text-muted-foreground">
                    {item.required_cases_reviewed}/{item.required_cases_total} case đã review
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
