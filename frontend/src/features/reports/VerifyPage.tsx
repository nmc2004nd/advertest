import { CircleCheck, CircleX } from 'lucide-react'
import { useState } from 'react'
import { useParams } from 'react-router'

import { formatDateTime } from '@/admin/format'
import { ApiError } from '@/api/errors'
import { FormAlert } from '@/components/FormAlert'
import { LoadError } from '@/components/LoadError'
import type { VerifyInfo } from '@/contracts/api'
import { PublicLayout } from '@/layout/PublicLayout'

import { useVerifyInfo } from './api'
import { hasWebCrypto, verifyFile, type VerifyResult } from './hash'

const FORMAT_LABEL = { pdf: 'PDF', json: 'JSON' } as const

function HashLine({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd className="font-mono text-xs break-all">{value}</dd>
    </div>
  )
}

type Checked = { fileName: string; hash: string; result: VerifyResult }

export function VerifyPanel({
  info,
  webCrypto = hasWebCrypto(),
  initial = null,
}: {
  info: VerifyInfo
  webCrypto?: boolean
  initial?: Checked | null
}) {
  const [checked, setChecked] = useState<Checked | null>(initial)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const onFile = async (file: File | undefined) => {
    if (!file) return
    setBusy(true)
    setError(null)
    setChecked(null)
    try {
      const { hash, result } = await verifyFile(file, info)
      setChecked({ fileName: file.name, hash, result })
    } catch {
      setError('Không đọc được file.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <dl className="flex flex-col gap-3">
        <HashLine label="Mã report" value={info.report_id} />
        <div>
          <dt className="text-sm text-muted-foreground">Ngày phát hành</dt>
          <dd>{formatDateTime(info.issued_at)}</dd>
        </div>
        <HashLine label="SHA-256 của PDF" value={info.pdf_sha256} />
        <HashLine label="SHA-256 của JSON" value={info.json_sha256} />
      </dl>
      {webCrypto ? (
        <div className="flex flex-col gap-1.5">
          <label htmlFor="file-xac-minh" className="text-sm font-medium">
            Chọn file PDF hoặc JSON của report
          </label>
          <input
            id="file-xac-minh"
            type="file"
            accept=".pdf,.json,application/pdf,application/json"
            disabled={busy}
            onChange={(event) => void onFile(event.target.files?.[0])}
            className="min-h-11 text-base file:mr-3 file:min-h-11 file:rounded-lg file:border file:border-input file:bg-background file:px-3"
          />
          <p className="text-sm text-muted-foreground">
            Hash được tính ngay trên máy của bạn; file không được gửi đi đâu.
          </p>
        </div>
      ) : (
        <FormAlert>
          Trình duyệt chỉ tính được hash khi trang mở qua HTTPS. Hãy mở lại trang này bằng địa chỉ
          https://.
        </FormAlert>
      )}
      {busy && <p className="text-muted-foreground">Đang tính hash…</p>}
      {error && <FormAlert>{error}</FormAlert>}
      {checked && (
        <section
          aria-live="polite"
          data-testid="ket-qua-xac-minh"
          className={
            checked.result.match
              ? 'flex flex-col gap-2 rounded-xl border border-emerald-600 p-4'
              : 'flex flex-col gap-2 rounded-xl border border-destructive p-4'
          }
        >
          <p className="flex items-center gap-2 text-lg font-semibold">
            {checked.result.match ? (
              <>
                <CircleCheck aria-hidden className="size-5 text-emerald-600" />
                Khớp
              </>
            ) : (
              <>
                <CircleX aria-hidden className="size-5 text-destructive" />
                Không khớp
              </>
            )}
          </p>
          <p className="text-sm break-all">
            {checked.result.match
              ? `${checked.fileName} đúng là file ${FORMAT_LABEL[checked.result.format]} của report này.`
              : `${checked.fileName} không trùng với file nào của report này: file đã bị sửa hoặc không phải report này.`}
          </p>
          <HashLine label="SHA-256 của file đã chọn" value={checked.hash} />
        </section>
      )}
    </div>
  )
}

/** Trang công khai `/verify/:id` (requirements.md Phase 8, Frontend công khai; plan task 33). */
export function VerifyPage() {
  const { id = '' } = useParams()
  const info = useVerifyInfo(id)
  return (
    <PublicLayout title="Xác minh report">
      {info.isPending ? (
        <p className="text-muted-foreground">Đang tải…</p>
      ) : info.isError ? (
        info.error instanceof ApiError && info.error.status === 404 ? (
          <FormAlert>
            Không có report chính thức với mã này. Kiểm tra lại mã in ở chân trang report.
          </FormAlert>
        ) : (
          <LoadError onRetry={() => void info.refetch()} retrying={info.isFetching} />
        )
      ) : (
        <VerifyPanel info={info.data} />
      )}
    </PublicLayout>
  )
}
