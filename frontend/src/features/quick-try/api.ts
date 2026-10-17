/** Dữ liệu của trang thử nhanh (requirements.md Phase R3, mục Thử nhanh). */
import { useMutation, useQuery } from '@tanstack/react-query'

import { ApiError, apiGet, apiPostForm } from '@/api/client'
import { POLL_INTERVAL_MS } from '@/api/queries'
import type { QuickTryView } from '@/contracts/api'

export type Preset = QuickTryView['preset']

export interface QuickTryInput {
  modelVersionId: string
  attackSpecId: string
  preset: Preset
  image: File
}

/** Tải ảnh mẫu thành `File` để gửi như ảnh người dùng chọn. */
export async function sampleFile(sample: { name: string; url: string }): Promise<File> {
  const res = await fetch(sample.url)
  if (!res.ok) throw new Error(`Không tải được ảnh mẫu (${res.status})`)
  const blob = await res.blob()
  return new File([blob], sample.name, { type: 'image/jpeg' })
}

const QUICK_TRY_KEY = ['quick-tries'] as const

/** Lượt `queued`/`running` tự cập nhật mỗi 2 giây; xong hoặc thất bại thì dừng. */
export function isPending(view: Pick<QuickTryView, 'status'> | undefined): boolean {
  return view?.status === 'queued' || view?.status === 'running'
}

/** Lỗi không nên thử lại: lượt đã hết hạn (410) hoặc không phải của mình (404). */
function noRetry(count: number, error: unknown): boolean {
  if (error instanceof ApiError && (error.status === 410 || error.status === 404)) return false
  return count < 3
}

export function useQuickTry(id: string | null) {
  return useQuery({
    queryKey: [...QUICK_TRY_KEY, id],
    queryFn: () => apiGet<QuickTryView>(`/quick-tries/${id ?? ''}`),
    enabled: id !== null,
    retry: noRetry,
    refetchInterval: (q) => (isPending(q.state.data) ? POLL_INTERVAL_MS : false),
  })
}

export function useCreateQuickTry() {
  return useMutation({
    mutationFn: (input: QuickTryInput) => {
      const form = new FormData()
      form.set('model_version_id', input.modelVersionId)
      form.set('attack_spec_id', input.attackSpecId)
      form.set('preset', input.preset)
      form.set('image', input.image)
      return apiPostForm<QuickTryView>('/quick-tries', form)
    },
  })
}

// API không trả id của lượt đang chạy khi gặp 429, nên trình duyệt nhớ lượt vừa tạo để link tới
// (người dùng chốt 2026-10-11). Chỉ là tiện ích: localStorage lỗi hoặc rỗng thì không có link.
const LAST_KEY = 'advertest-quick-try'

export function rememberQuickTry(userId: string, quickTryId: string): void {
  try {
    localStorage.setItem(`${LAST_KEY}:${userId}`, quickTryId)
  } catch {
    // Trình duyệt chặn localStorage: bỏ qua, 429 chỉ hiện câu thông báo.
  }
}

export function lastQuickTry(userId: string): string | null {
  try {
    return localStorage.getItem(`${LAST_KEY}:${userId}`)
  } catch {
    return null
  }
}
