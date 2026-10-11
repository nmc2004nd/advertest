import { useState } from 'react'
import { useNavigate } from 'react-router'

import { ApiError } from '@/api/errors'
import { errorMessage } from '@/api/messages'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { SelectField } from '@/components/form/TextField'
import type { ExperimentDetail } from '@/contracts/api'
import { usePromote, useProtocols } from '@/features/wizard/api'
import { draftFromClone, saveDraft } from '@/features/wizard/state'

import { PROMOTE_CONFLICT, PROMOTE_LABEL } from './results'

/**
 * "Nâng lên chính thức" (requirements.md Phase R3, Kết quả và insight): chọn protocol `active`, gọi
 * `POST /experiments/{id}/promote` (chỉ trả bản nháp), lưu nháp rồi mở wizard ở bước 3. Experiment
 * mới chỉ được tạo khi người dùng bấm "Tạo experiment" sau khi xem ước lượng (nguyên tắc 5).
 */
export function PromoteDialog({
  experiment,
  open,
  onOpenChange,
}: {
  experiment: ExperimentDetail
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const navigate = useNavigate()
  const protocols = useProtocols()
  const promote = usePromote(experiment.id)
  const [protocolId, setProtocolId] = useState('')
  const active = protocols.data?.filter((p) => p.status === 'active') ?? []
  const error = promote.error
  return (
    <ConfirmDialog
      open={open}
      onOpenChange={(value) => {
        if (!value) promote.reset()
        onOpenChange(value)
      }}
      title={PROMOTE_LABEL}
      description="Tạo bản nháp Chính thức với cùng model, slice và máy chạy; attack và level bắt buộc của protocol được thêm vào. Kết quả của experiment này không được chép sang."
      confirmLabel="Tiếp tục"
      pending={promote.isPending}
      canConfirm={protocolId !== ''}
      onConfirm={() =>
        promote.mutate(protocolId, {
          onSuccess: (result) => {
            saveDraft(
              draftFromClone(result.config, result.warnings, null, 'official', result.notes ?? []),
            )
            void navigate('/experiments/new')
          },
        })
      }
    >
      <div className="space-y-3">
        {active.length === 0 && !protocols.isPending ? (
          <p role="alert" className="text-sm text-destructive">
            Chưa có protocol nào đang dùng. Reviewer cần tạo protocol trước.
          </p>
        ) : (
          <SelectField
            id="promote-protocol"
            label="Protocol"
            value={protocolId}
            onChange={(event) => setProtocolId(event.target.value)}
          >
            <option value="" disabled>
              Chọn protocol
            </option>
            {active.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} v{p.version}
              </option>
            ))}
          </SelectField>
        )}
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error instanceof ApiError && error.status === 409
              ? `${errorMessage(error)} ${PROMOTE_CONFLICT}`
              : errorMessage(error)}
          </p>
        )}
      </div>
    </ConfirmDialog>
  )
}
