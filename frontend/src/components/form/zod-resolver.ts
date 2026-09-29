import type { FieldError, FieldErrors, FieldValues, Resolver } from 'react-hook-form'
import type { z } from 'zod'

/**
 * Resolver react-hook-form ↔ zod (tự viết thay `@hookform/resolvers`, không thêm dependency;
 * người dùng chốt ở Phase 4 Group 4). Mỗi trường giữ lỗi đầu tiên theo đường dẫn của zod.
 */
export function zodResolver<Schema extends z.ZodType<FieldValues, FieldValues>>(
  schema: Schema,
): Resolver<z.input<Schema>, unknown, z.output<Schema>> {
  return async (values) => {
    const result = await schema.safeParseAsync(values)
    if (result.success) return { values: result.data, errors: {} }
    const errors: Record<string, unknown> = {}
    for (const issue of result.error.issues) {
      const path = issue.path.map(String)
      if (path.length === 0) path.push('root')
      setFirst(errors, path, { type: issue.code, message: issue.message })
    }
    return { values: {}, errors: errors as FieldErrors<z.input<Schema>> }
  }
}

function setFirst(target: Record<string, unknown>, path: string[], error: FieldError): void {
  let node = target
  for (const key of path.slice(0, -1)) {
    const next = node[key]
    if (typeof next !== 'object' || next === null) node[key] = {}
    node = node[key] as Record<string, unknown>
  }
  const last = path[path.length - 1]
  if (!(last in node)) node[last] = error
}
