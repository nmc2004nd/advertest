import { CircleCheck, CircleDashed, CircleX } from 'lucide-react'

import type { SpecCheckResult } from '@/contracts/api'
import { specCheckNameValues } from '@/contracts/schemas'
import { SPEC_CHECK_LABEL } from '@/copy/catalog'

import { formatDateTime } from './format'

/**
 * Kết quả tự kiểm tra: 7 mục theo thứ tự `SpecCheckName`, mỗi mục đạt/không đạt kèm `details`;
 * mục không chạy tới (quá giờ, lỗi giữa chừng) ghi rõ, cộng `error` nếu có.
 */
export function SpecCheckList({ check }: { check: SpecCheckResult | null | undefined }) {
  if (!check) {
    return <p className="text-sm text-muted-foreground">Chưa có kết quả tự kiểm tra.</p>
  }
  return (
    <div className="flex flex-col gap-3">
      <ol className="flex flex-col divide-y divide-border rounded-xl border border-border">
        {specCheckNameValues.map((name) => {
          const item = check.items.find((i) => i.name === name)
          const state = item ? (item.passed ? 'passed' : 'failed') : 'missing'
          const Icon =
            state === 'passed' ? CircleCheck : state === 'failed' ? CircleX : CircleDashed
          return (
            <li
              key={name}
              data-testid="check-item"
              data-check={name}
              data-state={state}
              className="flex items-start gap-3 px-3 py-2.5"
            >
              <Icon
                aria-hidden
                className={
                  state === 'passed'
                    ? 'mt-0.5 size-4 shrink-0 text-approved'
                    : state === 'failed'
                      ? 'mt-0.5 size-4 shrink-0 text-fail'
                      : 'mt-0.5 size-4 shrink-0 text-muted-foreground'
                }
              />
              <div className="flex min-w-0 flex-col gap-0.5">
                <span className="text-sm font-semibold">
                  {SPEC_CHECK_LABEL[name].label}{' '}
                  <span className="font-normal text-muted-foreground">
                    ·{' '}
                    {state === 'passed'
                      ? 'Đạt'
                      : state === 'failed'
                        ? 'Không đạt'
                        : 'Không chạy tới'}
                  </span>
                </span>
                <span className="text-[13px] text-muted-foreground">
                  {item?.details ?? SPEC_CHECK_LABEL[name].hint}
                </span>
              </div>
            </li>
          )
        })}
      </ol>
      {check.error && (
        <p role="note" className="text-sm text-fail">
          Lỗi: {check.error}
        </p>
      )}
      <p className="text-xs text-muted-foreground">
        Kiểm tra lúc {formatDateTime(check.checked_at)}
      </p>
    </div>
  )
}
