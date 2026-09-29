import { Check, Copy } from 'lucide-react'
import { useState } from 'react'

import { middleTruncate } from '@/admin/format'
import { Button } from '@/components/ui/button'

/**
 * Copy vào clipboard. Trang HTTP mở qua mạng LAN trên điện thoại không có `navigator.clipboard`:
 * khi đó chọn sẵn chữ trong ô `targetId` (nếu có) để người dùng tự copy.
 */
export function CopyButton({
  value,
  label = 'Copy',
  targetId,
}: {
  value: string
  label?: string
  targetId?: string
}) {
  const [state, setState] = useState<'idle' | 'copied' | 'manual'>('idle')
  const copy = async () => {
    try {
      if (!navigator.clipboard) throw new Error('Không có clipboard')
      await navigator.clipboard.writeText(value)
      setState('copied')
    } catch {
      const target = targetId ? document.getElementById(targetId) : null
      if (target instanceof HTMLInputElement) target.select()
      setState('manual')
    }
  }
  return (
    <span className="inline-flex items-center gap-2">
      <Button
        type="button"
        variant="outline"
        size={label ? 'default' : 'icon'}
        onClick={() => void copy()}
        aria-label={label ? undefined : 'Copy'}
      >
        {state === 'copied' ? <Check aria-hidden /> : <Copy aria-hidden />}
        {label && (state === 'copied' ? 'Đã copy' : label)}
      </Button>
      {state === 'manual' && (
        <span role="status" className="text-sm text-muted-foreground">
          Trình duyệt không cho copy tự động: đã chọn sẵn, hãy copy thủ công.
        </span>
      )}
    </span>
  )
}

/** Chuỗi dài rút gọn ở giữa, kèm nút copy giá trị đầy đủ. */
export function TruncatedId({ value }: { value: string }) {
  const short = middleTruncate(value)
  return (
    <span className="inline-flex items-center gap-1">
      <code className="font-mono text-xs" title={value}>
        {short}
      </code>
      <CopyButton value={value} label="" />
    </span>
  )
}
