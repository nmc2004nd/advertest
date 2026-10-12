import { FileCog } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { errorMessage } from '@/api/messages'
import { type ConvertFramework, guessConvertFramework } from '@/admin/model-file'
import { useConversion, useStartConversion } from '@/admin/useModelAdmin'
import { FormAlert } from '@/components/FormAlert'
import { SelectField } from '@/components/form/TextField'
import { Button } from '@/components/ui/button'
import type { ModelConversionView } from '@/contracts/api'
import { MODEL_ADMIN_COPY } from '@/copy/model-admin'

/**
 * Chuyển `.pt`/`.pth` sang safetensors trong sandbox (đề xuất contract 003): tải file lên, tạo lượt
 * chuyển, theo dõi tới khi xong rồi gọi `onDone` với kết quả để form tự điền.
 */
export function ConvertPanel({
  file,
  onDone,
}: {
  file: File
  onDone: (view: ModelConversionView) => void
}) {
  const copy = MODEL_ADMIN_COPY
  const [framework, setFramework] = useState<ConvertFramework>(guessConvertFramework(file.name))
  const [progress, setProgress] = useState<number | null>(null)
  const start = useStartConversion(setProgress)
  const conversion = useConversion(start.data?.id ?? null)
  const view = conversion.data ?? start.data
  const reported = useRef<string | null>(null)

  useEffect(() => {
    if (view?.status === 'completed' && reported.current !== view.id) {
      reported.current = view.id
      onDone(view)
    }
  }, [view, onDone])

  const busy = start.isPending || view?.status === 'queued' || view?.status === 'running'
  const failed = start.isError || view?.status === 'failed'
  const status = start.isPending
    ? `Đang tải lên ${Math.round((progress ?? 0) * 100)}%`
    : view?.status === 'queued'
      ? copy.convertQueued
      : view?.status === 'running'
        ? copy.convertRunning
        : null

  return (
    <div
      data-testid="convert-panel"
      className="flex flex-col gap-3 rounded-lg border border-border bg-surface-raised p-3 text-sm"
    >
      <p className="flex items-center gap-2 font-semibold">
        <FileCog aria-hidden="true" className="size-4 shrink-0" />
        {copy.convertTitle}
      </p>
      <p className="text-muted-foreground">{copy.convertIntro}</p>
      {view?.status === 'completed' ? (
        <p role="status" className="text-approved">
          {copy.convertDone}
        </p>
      ) : (
        <div className="flex flex-col gap-3 md:flex-row md:items-end">
          <SelectField
            label={copy.convertFramework}
            value={framework}
            disabled={busy}
            onChange={(e) => setFramework(e.target.value as ConvertFramework)}
          >
            <option value="ultralytics">Checkpoint YOLO Ultralytics</option>
            <option value="torchvision">State dict torchvision</option>
          </SelectField>
          <Button
            type="button"
            disabled={busy}
            onClick={() => {
              start.reset()
              start.mutate({ file, framework })
            }}
          >
            {failed ? copy.convertRetry : copy.convertButton}
          </Button>
        </div>
      )}
      {status && (
        <p role="status" className="text-muted-foreground tabular-nums">
          {status}
        </p>
      )}
      {start.isError && <FormAlert>{errorMessage(start.error)}</FormAlert>}
      {view?.status === 'failed' && view.error && <FormAlert>{view.error}</FormAlert>}
    </div>
  )
}
