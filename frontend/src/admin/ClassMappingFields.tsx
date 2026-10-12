import { CONTROL_CLASS, SelectField } from '@/components/form/TextField'
import { MODEL_ADMIN_COPY } from '@/copy/model-admin'
import { cn } from '@/lib/utils'

import { mappedCount } from './class-mapping'
import type { Difficulty, MappingDraft } from './mapping-draft'

const SKIP = '__bo__'

/**
 * Chọn dataset, class đích cho từng class của dataset, và ngưỡng độ khó. Danh sách dọc (nhãn trái,
 * ô chọn phải) dùng được cả trên điện thoại.
 */
export function ClassMappingFields({
  draft,
  modelClasses,
  showError,
}: {
  draft: MappingDraft
  modelClasses: readonly string[]
  showError: boolean
}) {
  const copy = MODEL_ADMIN_COPY
  if (draft.options.length === 0) {
    return <p className="text-sm text-muted-foreground">{copy.noDataset}</p>
  }
  return (
    <div className="flex flex-col gap-3">
      <div className="grid gap-4 md:grid-cols-2">
        <SelectField
          label="Dataset"
          value={draft.versionId ?? ''}
          onChange={(e) => draft.setVersionId(e.target.value)}
        >
          {draft.options.map((o) => (
            <option key={o.id} value={o.id}>
              {o.label}
            </option>
          ))}
        </SelectField>
        <SelectField
          label="Lọc theo độ khó"
          hint={copy.difficultyHint}
          value={draft.difficulty}
          onChange={(e) => draft.setDifficulty(e.target.value as Difficulty)}
        >
          <option value="moderate">{copy.moderate}</option>
          <option value="none">Không lọc</option>
        </SelectField>
      </div>
      <div className="flex flex-col gap-1.5">
        <p className="text-[14px] font-semibold">
          Class của dataset → class của model ({mappedCount(draft.classes)}/
          {draft.datasetClasses.length} được tính)
        </p>
        <p className="text-[13px] leading-5 text-muted-foreground">{copy.mappingHint}</p>
        <ul className="divide-y divide-border rounded-lg border border-line" data-testid="mapping">
          {draft.datasetClasses.map((source) => {
            const target = draft.classes[source] ?? null
            return (
              <li
                key={source}
                className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)] items-center gap-3 px-3 py-1.5"
              >
                <label htmlFor={`map-${source}`} className="truncate text-sm font-medium">
                  {source}
                </label>
                <select
                  id={`map-${source}`}
                  value={target ?? SKIP}
                  onChange={(e) =>
                    draft.setTarget(source, e.target.value === SKIP ? null : e.target.value)
                  }
                  className={cn(CONTROL_CLASS, 'min-h-11')}
                >
                  <option value={SKIP}>Bỏ qua (vùng bỏ qua khi chấm)</option>
                  {modelClasses.map((name) => (
                    <option key={name} value={name}>
                      {name}
                    </option>
                  ))}
                </select>
              </li>
            )
          })}
        </ul>
        {showError && draft.error && (
          <p role="alert" className="text-[13px] text-fail">
            {draft.error}
          </p>
        )}
      </div>
    </div>
  )
}
