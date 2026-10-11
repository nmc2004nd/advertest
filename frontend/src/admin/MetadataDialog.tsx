import { useState } from 'react'

import { errorMessage } from '@/api/messages'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { FormAlert } from '@/components/FormAlert'
import { SelectField, TextareaField, TextField } from '@/components/form/TextField'
import type { AttackSpecAdminView } from '@/contracts/api'
import { REALISM_LABEL } from '@/copy/catalog'

import { parseLevelLabels, prefillFrom, type Realism } from './spec-form'
import { useUpdateSpecMetadata } from './useSpecAdmin'

/** Sửa metadata của spec (không đổi hash, không đổi version). */
export function MetadataDialog({
  spec,
  onClose,
}: {
  spec: AttackSpecAdminView
  onClose: () => void
}) {
  const initial = prefillFrom(spec)
  const [displayName, setDisplayName] = useState(initial.displayName)
  const [description, setDescription] = useState(initial.description)
  const [realism, setRealism] = useState<Realism>(initial.realism)
  const [levelLabels, setLevelLabels] = useState(initial.levelLabels)
  const update = useUpdateSpecMetadata()
  const labels = parseLevelLabels(levelLabels)
  const valid = displayName.trim() !== '' && description.trim() !== '' && !(labels instanceof Error)
  return (
    <ConfirmDialog
      open
      onOpenChange={(open) => !open && onClose()}
      title="Sửa thông tin hiển thị"
      description={`${spec.name} v${spec.version}. Thông tin này không thuộc hash của spec.`}
      confirmLabel="Lưu"
      pending={update.isPending}
      canConfirm={valid}
      onConfirm={() => {
        if (labels instanceof Error) return
        update.mutate(
          {
            id: spec.id,
            metadata: {
              display_name: displayName.trim(),
              description: description.trim(),
              realism,
              level_labels: labels,
            },
          },
          { onSuccess: onClose },
        )
      }}
    >
      <div className="flex flex-col gap-3">
        <TextField
          label="Tên hiển thị"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
        />
        <TextareaField
          label="Mô tả"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
        <SelectField
          label="Mức sát thực tế"
          value={realism}
          onChange={(e) => setRealism(e.target.value as Realism)}
        >
          {(Object.keys(REALISM_LABEL) as Realism[]).map((r) => (
            <option key={r} value={r}>
              {REALISM_LABEL[r]}
            </option>
          ))}
        </SelectField>
        <TextareaField
          label="Nhãn level"
          hint='Mỗi dòng "level: nhãn".'
          error={labels instanceof Error ? labels.message : undefined}
          value={levelLabels}
          onChange={(e) => setLevelLabels(e.target.value)}
        />
      </div>
      {update.isError && <FormAlert>{errorMessage(update.error)}</FormAlert>}
    </ConfirmDialog>
  )
}
