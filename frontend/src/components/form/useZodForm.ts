import { useForm, type FieldValues, type UseFormProps } from 'react-hook-form'
import type { z } from 'zod'

import { zodResolver } from './zod-resolver'

/** `useForm` với schema zod; kiểm tra khi rời ô nhập, rồi kiểm tra lại mỗi lần sửa. */
export function useZodForm<Schema extends z.ZodType<FieldValues, FieldValues>>(
  schema: Schema,
  options: Omit<UseFormProps<z.input<Schema>, unknown, z.output<Schema>>, 'resolver'> = {},
) {
  return useForm<z.input<Schema>, unknown, z.output<Schema>>({
    mode: 'onTouched',
    ...options,
    resolver: zodResolver(schema),
  })
}
