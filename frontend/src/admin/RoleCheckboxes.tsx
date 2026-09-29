import { ROLE_LABELS } from '@/auth/roles'
import { roleValues, type Role } from '@/contracts/schemas'

/** Chọn role bằng checkbox; mỗi dòng cao ≥ 44px để dễ chạm. */
export function RoleCheckboxes({
  value,
  onChange,
  legend,
}: {
  value: Role[]
  onChange: (roles: Role[]) => void
  legend: string
}) {
  const toggle = (role: Role, checked: boolean) =>
    onChange(
      checked
        ? roleValues.filter((r) => r === role || value.includes(r))
        : value.filter((r) => r !== role),
    )
  return (
    <fieldset className="flex flex-col gap-1">
      <legend className="mb-1 text-sm font-medium">{legend}</legend>
      {roleValues.map((role) => (
        <label
          key={role}
          className="flex min-h-11 items-center gap-3 rounded-lg px-1 hover:bg-muted"
        >
          <input
            type="checkbox"
            className="size-5"
            checked={value.includes(role)}
            onChange={(event) => toggle(role, event.target.checked)}
          />
          <span className="text-base">{ROLE_LABELS[role]}</span>
        </label>
      ))}
    </fieldset>
  )
}
