import { Crosshair, ListChecks, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'

import { ApiError } from '@/api/errors'
import { errorMessage } from '@/api/messages'
import { THRESHOLD_KIND_LABEL } from '@/components/charts/breakpoints'
import { AttackRisk, AttackTile } from '@/components/AttackTile'
import { FormAlert } from '@/components/FormAlert'
import { SelectField, TextareaField, TextField } from '@/components/form/TextField'
import { Button } from '@/components/ui/button'
import type { AttackSpec, ProtocolBody, ProtocolTemplate, ThresholdKind } from '@/contracts/api'
import { ATTACK_EXPLAIN, ATTACK_PLAIN } from '@/lib/attack-kinds'

import { fetchTemplateDraft } from './api'

import {
  type AttackRow,
  buildProtocol,
  type CriterionRow,
  EMPTY_ATTACK,
  EMPTY_CRITERION,
  formOf,
  formPath,
  isShownPath,
  parseLevels,
  type ProtocolForm,
} from './form'
import { AttackLevelChips, CriterionLevelChips } from './LevelChips'
import { TemplatePicker } from './TemplatePicker'

const CRITERION_KIND_LABEL = {
  max_drop_at_level: 'Mức sụt tối đa tại một level (quét lưới)',
  min_breaking_point: 'Điểm gãy tối thiểu (tìm ngưỡng)',
} as const

function ThresholdOptions() {
  return (
    <>
      {(Object.keys(THRESHOLD_KIND_LABEL) as ThresholdKind[]).map((k) => (
        <option key={k} value={k}>
          {THRESHOLD_KIND_LABEL[k]}
        </option>
      ))}
    </>
  )
}

function AttackFields({
  row,
  index,
  specs,
  errors,
  onChange,
  onRemove,
}: {
  row: AttackRow
  index: number
  specs: AttackSpec[]
  errors: Record<string, string>
  onChange: (row: AttackRow) => void
  onRemove: () => void
}) {
  const id = `attack-${index}`
  const err = (field: string) => errors[`attacks.${index}.${field}`] ?? errors[`attacks.${index}`]
  const set = (patch: Partial<AttackRow>) => onChange({ ...row, ...patch })
  const spec = specs.find((s) => s.name === row.name)
  const how = spec && (ATTACK_EXPLAIN[spec.name]?.how ?? ATTACK_PLAIN[spec.name])
  return (
    <fieldset className="space-y-3 rounded-lg border p-3">
      <legend className="px-1 text-sm font-medium">Attack {index + 1}</legend>
      {spec && (
        <div className="flex items-start gap-3">
          <AttackTile spec={spec} />
          <div className="flex min-w-0 flex-1 flex-col gap-0.5">
            <p className="font-semibold">
              {spec.name}{' '}
              <span className="text-xs font-normal text-muted-foreground">v{spec.version}</span>
            </p>
            {how && <p className="text-[13px] leading-5 text-muted-foreground">{how}</p>}
            <AttackRisk name={spec.name} />
          </div>
        </div>
      )}
      <div className="grid gap-3 md:grid-cols-2">
        <SelectField
          id={`${id}-ten`}
          label="Attack"
          value={row.name}
          error={err('name')}
          onChange={(e) => set({ name: e.target.value, levels: '' })}
        >
          <option value="">Chọn…</option>
          {specs.map((s) => (
            <option key={s.id} value={s.name}>
              {s.name} (v{s.version})
            </option>
          ))}
        </SelectField>
        <SelectField
          id={`${id}-che-do`}
          label="Chế độ"
          value={row.mode}
          error={errors[`attacks.${index}.mode`]}
          onChange={(e) => set({ mode: e.target.value as AttackRow['mode'] })}
        >
          <option value="grid">Quét lưới</option>
          <option value="search">Tìm ngưỡng</option>
        </SelectField>
      </div>
      {row.mode === 'grid' ? (
        <AttackLevelChips
          idBase={id}
          spec={spec}
          value={row.levels}
          error={errors[`attacks.${index}.levels`]}
          onChange={(levels) => set({ levels })}
        />
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          <SelectField
            id={`${id}-loai-nguong`}
            label="Loại ngưỡng"
            value={row.thresholdKind}
            onChange={(e) => set({ thresholdKind: e.target.value as ThresholdKind })}
          >
            <ThresholdOptions />
          </SelectField>
          <TextField
            id={`${id}-nguong`}
            label="Ngưỡng (%)"
            placeholder="30"
            hint="Mức sụt mAP coi là model gãy."
            inputMode="decimal"
            value={row.threshold}
            error={errors[`attacks.${index}.threshold`]}
            onChange={(e) => set({ threshold: e.target.value })}
          />
          <TextField
            id={`${id}-class`}
            label="Class (không bắt buộc)"
            placeholder="Bỏ trống để tính mọi class, ví dụ: car"
            value={row.classFilter}
            onChange={(e) => set({ classFilter: e.target.value })}
          />
          <TextField
            id={`${id}-bootstrap`}
            label="Số mẫu bootstrap tối thiểu"
            placeholder="1000"
            inputMode="numeric"
            value={row.minBootstrap}
            error={errors[`attacks.${index}.minBootstrap`]}
            onChange={(e) => set({ minBootstrap: e.target.value })}
          />
          <TextField
            id={`${id}-lo`}
            label="Cận dưới (lo)"
            placeholder="Ví dụ: 1"
            inputMode="decimal"
            value={row.lo}
            error={errors[`attacks.${index}.lo`]}
            onChange={(e) => set({ lo: e.target.value })}
          />
          <TextField
            id={`${id}-hi`}
            label="Cận trên (hi)"
            placeholder="Ví dụ: 32"
            inputMode="decimal"
            value={row.hi}
            onChange={(e) => set({ hi: e.target.value })}
          />
          <TextField
            id={`${id}-tol`}
            label="Sai số tối đa (max_tol)"
            placeholder="Ví dụ: 1"
            inputMode="decimal"
            value={row.maxTol}
            error={errors[`attacks.${index}.maxTol`]}
            onChange={(e) => set({ maxTol: e.target.value })}
          />
        </div>
      )}
      <Button type="button" variant="ghost" onClick={onRemove}>
        <Trash2 aria-hidden="true" />
        Bỏ attack {index + 1}
      </Button>
    </fieldset>
  )
}

function CriterionFields({
  row,
  index,
  attacks,
  errors,
  onChange,
  onRemove,
}: {
  row: CriterionRow
  index: number
  attacks: AttackRow[]
  errors: Record<string, string>
  onChange: (row: CriterionRow) => void
  onRemove: () => void
}) {
  const id = `tieu-chi-${index}`
  const err = (field: string) => errors[`criteria.${index}.${field}`]
  const set = (patch: Partial<CriterionRow>) => onChange({ ...row, ...patch })
  const grid = row.kind === 'max_drop_at_level'
  return (
    <fieldset className="space-y-3 rounded-lg border p-3">
      <legend className="px-1 text-sm font-medium">Tiêu chí {index + 1}</legend>
      {errors[`criteria.${index}`] && <FormAlert>{errors[`criteria.${index}`]}</FormAlert>}
      <div className="grid gap-3 md:grid-cols-2">
        <SelectField
          id={`${id}-loai`}
          label="Loại tiêu chí"
          value={row.kind}
          error={err('kind')}
          onChange={(e) => set({ kind: e.target.value as CriterionRow['kind'] })}
        >
          {(Object.keys(CRITERION_KIND_LABEL) as CriterionRow['kind'][]).map((k) => (
            <option key={k} value={k}>
              {CRITERION_KIND_LABEL[k]}
            </option>
          ))}
        </SelectField>
        <SelectField
          id={`${id}-attack`}
          label="Attack"
          value={row.attackName}
          error={err('attackName')}
          onChange={(e) => set({ attackName: e.target.value, level: '' })}
        >
          <option value="">Chọn…</option>
          {attacks
            .filter((a) => a.name)
            .map((a) => (
              <option key={a.name} value={a.name}>
                {a.name}
              </option>
            ))}
        </SelectField>
        {grid ? (
          <CriterionLevelChips
            idBase={id}
            levels={parseLevels(attacks.find((a) => a.name === row.attackName)?.levels ?? '')}
            value={row.level}
            error={err('level')}
            onChange={(level) => set({ level })}
          />
        ) : (
          <TextField
            id={`${id}-level`}
            label="Điểm gãy tối thiểu"
            placeholder="Ví dụ: 4"
            inputMode="decimal"
            value={row.level}
            error={err('level')}
            onChange={(e) => set({ level: e.target.value })}
          />
        )}
        {grid && (
          <>
            <SelectField
              id={`${id}-loai-nguong`}
              label="Loại ngưỡng"
              value={row.thresholdKind}
              onChange={(e) => set({ thresholdKind: e.target.value as ThresholdKind })}
            >
              <ThresholdOptions />
            </SelectField>
            <TextField
              id={`${id}-nguong`}
              label="Mức sụt tối đa (%)"
              placeholder="30"
              inputMode="decimal"
              value={row.threshold}
              error={err('threshold')}
              onChange={(e) => set({ threshold: e.target.value })}
            />
            <TextField
              id={`${id}-class`}
              label="Class (không bắt buộc)"
              placeholder="Bỏ trống để tính mọi class"
              value={row.classFilter}
              onChange={(e) => set({ classFilter: e.target.value })}
            />
          </>
        )}
      </div>
      {!grid && (
        <p className="text-sm text-muted-foreground">
          Ngưỡng và class lấy theo cấu hình tìm ngưỡng của attack.
        </p>
      )}
      <Button type="button" variant="ghost" onClick={onRemove}>
        <Trash2 aria-hidden="true" />
        Bỏ tiêu chí {index + 1}
      </Button>
    </fieldset>
  )
}

/**
 * Form protocol (plan task 30). `lockName` khi tạo version mới: tên giữ nguyên. Lỗi 422 của
 * server hiện tại đúng trường khi ánh xạ được, còn lại hiện ở đầu form.
 */
export function ProtocolEditor({
  initial,
  lockName = false,
  specs,
  pending,
  error,
  submitLabel,
  templates,
  onSubmit,
  onCancel,
}: {
  initial: ProtocolForm
  lockName?: boolean
  specs: AttackSpec[]
  pending: boolean
  error: unknown
  submitLabel: string
  /** Khi tạo protocol mới: thẻ mẫu điền sẵn form (`GET /protocol-templates/{key}/draft`). */
  templates?: ProtocolTemplate[]
  onSubmit: (name: string, body: ProtocolBody) => void
  onCancel: () => void
}) {
  const [form, setForm] = useState<ProtocolForm>(initial)
  const [local, setLocal] = useState<Record<string, string>>({})
  const fields = error instanceof ApiError ? error.fields : []
  const server = Object.fromEntries(
    fields.map((f) => [formPath(f.path), f.message]).filter(([path]) => isShownPath(path)),
  )
  const unplaced = fields.filter((f) => !isShownPath(formPath(f.path))).map((f) => f.message)
  const errors = { ...server, ...local }
  const [template, setTemplate] = useState<ProtocolTemplate['key'] | null>(null)
  const [loadingTemplate, setLoadingTemplate] = useState<ProtocolTemplate['key'] | null>(null)
  const [templateError, setTemplateError] = useState<string | null>(null)
  const pickTemplate = async (key: ProtocolTemplate['key']) => {
    setLoadingTemplate(key)
    setTemplateError(null)
    try {
      const draft = await fetchTemplateDraft(key)
      // Tên protocol không được trùng: thêm ngày tạo vào tên gợi ý của mẫu.
      setForm(formOf(`${draft.name} ${new Date().toISOString().slice(0, 10)}`, draft.body))
      setLocal({})
      setTemplate(key)
    } catch (e) {
      setTemplateError(errorMessage(e))
    } finally {
      setLoadingTemplate(null)
    }
  }
  const set = (patch: Partial<ProtocolForm>) => setForm((f) => ({ ...f, ...patch }))
  const setAttack = (i: number, row: AttackRow) =>
    set({ attacks: form.attacks.map((a, j) => (j === i ? row : a)) })
  const setCriterion = (i: number, row: CriterionRow) =>
    set({ criteria: form.criteria.map((c, j) => (j === i ? row : c)) })

  const submit = (event: React.FormEvent) => {
    event.preventDefault()
    const result = buildProtocol(form, specs)
    if (!result.ok) {
      setLocal(result.errors)
      return
    }
    setLocal({})
    onSubmit(result.name, result.body)
  }

  return (
    <form className="space-y-4" onSubmit={submit} noValidate>
      {error !== null && error !== undefined && fields.length === 0 && (
        <FormAlert>{errorMessage(error)}</FormAlert>
      )}
      {unplaced.length > 0 && (
        <FormAlert>
          <ul>
            {unplaced.map((message) => (
              <li key={message}>{message}</li>
            ))}
          </ul>
        </FormAlert>
      )}
      {templates && (
        <TemplatePicker
          templates={templates}
          selected={template}
          loading={loadingTemplate}
          error={templateError}
          onPick={(key) => void pickTemplate(key)}
        />
      )}
      {Object.keys(local).length > 0 && (
        <FormAlert>Còn {Object.keys(local).length} trường chưa hợp lệ.</FormAlert>
      )}
      <TextField
        id="protocol-ten"
        label="Tên protocol"
        placeholder="Ví dụ: KITTI xe con, ban ngày"
        autoFocus={!lockName}
        value={form.name}
        disabled={lockName}
        error={errors.name}
        onChange={(e) => set({ name: e.target.value })}
      />
      <TextareaField
        id="protocol-mo-ta"
        label="Mục đích"
        placeholder="Protocol này kiểm định điều gì, cho model nào, trước mốc nào. Ví dụ: chặn phát hành YOLOv8 nếu sụt quá 30% mAP ở PGD eps 8."
        value={form.description}
        error={errors.description}
        onChange={(e) => set({ description: e.target.value })}
      />
      <div className="grid gap-3 md:grid-cols-2">
        <TextField
          id="protocol-slice"
          label="Kích thước slice tối thiểu"
          placeholder="300"
          hint="Experiment dùng slice nhỏ hơn sẽ không gửi duyệt được."
          inputMode="numeric"
          value={form.minSliceSize}
          error={errors.minSliceSize}
          onChange={(e) => set({ minSliceSize: e.target.value })}
        />
        <TextField
          id="protocol-so-case"
          label="Số case bắt buộc review mỗi attack"
          placeholder="5"
          hint="Reviewer phải xem đủ số case này trước khi chấp nhận."
          inputMode="numeric"
          value={form.casesPerAttack}
          error={errors.casesPerAttack}
          onChange={(e) => set({ casesPerAttack: e.target.value })}
        />
      </div>
      <label className="flex min-h-11 items-center gap-2 text-sm">
        <input
          type="checkbox"
          className="size-5"
          checked={form.forbidDirty}
          onChange={(e) => set({ forbidDirty: e.target.checked })}
        />
        Không chấp nhận run chạy từ code chưa commit
      </label>

      <section className="space-y-2" aria-label="Attack bắt buộc">
        <h3 className="flex items-center gap-2 font-medium">
          <Crosshair aria-hidden="true" className="size-4 text-muted-foreground" />
          Attack bắt buộc
        </h3>
        {errors.attacks && <FormAlert>{errors.attacks}</FormAlert>}
        {form.attacks.map((row, i) => (
          <AttackFields
            key={i}
            row={row}
            index={i}
            specs={specs}
            errors={errors}
            onChange={(next) => setAttack(i, next)}
            onRemove={() => set({ attacks: form.attacks.filter((_, j) => j !== i) })}
          />
        ))}
        <Button
          type="button"
          variant="outline"
          onClick={() => set({ attacks: [...form.attacks, { ...EMPTY_ATTACK }] })}
        >
          <Plus aria-hidden="true" />
          Thêm attack
        </Button>
      </section>

      <section className="space-y-2" aria-label="Tiêu chí đạt">
        <h3 className="flex items-center gap-2 font-medium">
          <ListChecks aria-hidden="true" className="size-4 text-muted-foreground" />
          Tiêu chí đạt
        </h3>
        {errors.criteria && <FormAlert>{errors.criteria}</FormAlert>}
        {form.criteria.map((row, i) => (
          <CriterionFields
            key={i}
            row={row}
            index={i}
            attacks={form.attacks}
            errors={errors}
            onChange={(next) => setCriterion(i, next)}
            onRemove={() => set({ criteria: form.criteria.filter((_, j) => j !== i) })}
          />
        ))}
        <Button
          type="button"
          variant="outline"
          onClick={() => set({ criteria: [...form.criteria, { ...EMPTY_CRITERION }] })}
        >
          <Plus aria-hidden="true" />
          Thêm tiêu chí
        </Button>
      </section>

      <div className="flex flex-col gap-2 md:flex-row">
        <Button type="submit" disabled={pending}>
          {pending ? 'Đang lưu…' : submitLabel}
        </Button>
        <Button type="button" variant="outline" onClick={onCancel}>
          Hủy
        </Button>
      </div>
    </form>
  )
}
